"""Runs the four steps: research -> draft -> QC 1 (facts) + QC 2 (teaching).

Each step saves its own output, so a failure only needs that step to be
retried. The two QC layers are independent: they use different prompts,
neither sees the other's report, and QC 2 never sees the sources.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Any

from . import checks, db, llm, prompts
from .config import settings
from .research import ResearchError, run_research
from .timing import MINUTES, estimate

log = logging.getLogger("lectern.pipeline")

_running: set[str] = set()
_guard = threading.Lock()

LENGTH_PASS_BELOW = 40  # minutes
VERDICTS = {"supported", "well_established", "unsupported", "misleading", "incorrect"}
SEVERITIES = ("high", "medium", "low")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def is_busy(lesson_id: str) -> bool:
    return lesson_id in _running


def plan_for(lesson: dict[str, Any], step: str) -> list[str]:
    """Which steps to run when the instructor (re)starts `step`."""
    status = {k: v.get("status") for k, v in lesson["steps"].items()}
    if step == "research":
        return ["research"] + [s for s in ("draft", "qc_facts", "qc_teaching") if status.get(s) != "done"]
    if step == "draft":
        return ["draft", "qc_facts", "qc_teaching"]
    return [step]


def start(lesson_id: str, steps: list[str]) -> bool:
    with _guard:
        if lesson_id in _running:
            return False
        _running.add(lesson_id)
    for s in steps:
        db.set_step(lesson_id, s, "pending")
    threading.Thread(target=_run, args=(lesson_id, steps), daemon=True).start()
    return True


def _run(lesson_id: str, steps: list[str]) -> None:
    try:
        for step in steps:
            _run_step(lesson_id, step)
    finally:
        with _guard:
            _running.discard(lesson_id)


def _run_step(lesson_id: str, step: str) -> None:
    lesson = db.get_lesson(lesson_id)
    if lesson is None:
        return
    blocked = _prerequisite_problem(lesson, step)
    if blocked:
        db.set_step(lesson_id, step, "blocked", blocked)
        return
    db.set_step(lesson_id, step, "running")
    try:
        {"research": _research, "draft": _draft, "qc_facts": _qc_facts, "qc_teaching": _qc_teaching}[step](lesson)
    except (llm.LLMError, ResearchError) as exc:
        db.set_step(lesson_id, step, "failed", str(exc))
    except Exception as exc:  # keep the server alive and tell the instructor
        log.exception("step %s failed for %s", step, lesson_id)
        db.set_step(lesson_id, step, "failed", f"Unexpected error: {exc.__class__.__name__}: {exc}")
    else:
        db.set_step(lesson_id, step, "done")


def _prerequisite_problem(lesson: dict[str, Any], step: str) -> str | None:
    if step == "draft" and not (lesson.get("research") and lesson["steps"]["research"]["status"] == "done"):
        return "Waiting for research to finish."
    if step.startswith("qc") and not lesson["content"].strip():
        return "Waiting for a lesson draft."
    if step == "qc_facts" and not lesson.get("research"):
        return "Fact check needs the research sources."
    return None


# ---------------------------------------------------------------- steps

def _research(lesson: dict[str, Any]) -> None:
    research = run_research(lesson["title"], lesson["objective"])
    db.update_lesson(lesson["id"], research=research)


def clean_markdown(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    first_h1 = re.search(r"^#\s", text, re.M)
    if first_h1 and first_h1.start() > 0:
        text = text[first_h1.start():]
    # Give each line of the header block (objective, time, prerequisites) its own paragraph.
    first_h2 = text.find("\n## ")
    if first_h2 > 0:
        head = re.sub(r"\n(?=\*\*)", "\n\n", text[:first_h2])
        text = re.sub(r"\n{3,}", "\n\n", head) + text[first_h2:]
    return repair_tables(text)


def repair_tables(text: str) -> str:
    """Make each table's separator row match its header's column count, which models often get wrong."""
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*", lines[i]) and "|" in lines[i - 1]:
            cols = len([c for c in lines[i - 1].strip().strip("|").split("|")])
            lines[i] = "| " + " | ".join(["---"] * cols) + " |"
    return "\n".join(lines)


def normalise_citations(text: str) -> str:
    """[S1, S3] -> [S1][S3] so every citation renders and checks the same way."""
    def split(m: re.Match[str]) -> str:
        return "".join(f"[{p}]" for p in re.split(r"\s*,\s*", m.group(1)))

    return re.sub(r"\[((?:[SBV]\d+)(?:\s*,\s*[SBV]\d+)+)\]", split, text)


def _draft(lesson: dict[str, Any]) -> None:
    text = llm.complete(prompts.WRITER_SYSTEM, prompts.writer_prompt(lesson), temperature=0.4)
    text = normalise_citations(clean_markdown(text))
    if len(text) < 1500 or text.count("\n## ") < 4:
        raise llm.LLMError("The draft came back incomplete (too short or missing sections). Retry this step.")
    note = "AI draft" if not lesson["content"] else "AI draft (regenerated; earlier text kept in history)"
    db.save_content(lesson["id"], text, note, "ai")

    # Models often write short. If the measured time falls well under 45 minutes,
    # rewrite only the thin sections once. The first draft stays in history.
    timing = estimate(text)
    if timing["estimated_total"] < LENGTH_PASS_BELOW and prompts.thin_sections(timing):
        try:
            longer = expand_sections(lesson, text, timing)
        except llm.LLMError as exc:
            log.warning("length pass failed, keeping first draft: %s", exc)
            longer = None
        if longer:
            after = estimate(longer)
            if after["words"] > timing["words"]:
                db.save_content(
                    lesson["id"], longer,
                    f"AI draft expanded to fit 45 min (measured {timing['estimated_total']:.0f} → {after['estimated_total']:.0f} min)",
                    "ai",
                )
    # Older reviews no longer describe this text.
    db.update_lesson(lesson["id"], qc_facts=None, qc_teaching=None)


def section_bodies(text: str) -> dict[str, tuple[str, str]]:
    """Map the cleaned heading (as timing reports it) to (heading line, body)."""
    out = {}
    matches = list(re.finditer(r"^##\s+(?!#)(.+?)\s*$", text, re.M))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clean = MINUTES.sub("", m.group(1)).strip(" -–:")
        out[clean] = (m.group(0).lstrip("# ").strip(), text[m.end():end])
    return out


def expand_sections(lesson: dict[str, Any], text: str, timing: dict[str, Any]) -> str | None:
    bodies = section_bodies(text)
    data = llm.complete_json(prompts.WRITER_SYSTEM, prompts.expand_prompt(lesson, text, timing, bodies), temperature=0.4)
    by_line = {line.lower(): clean for clean, (line, _) in bodies.items()}
    changed = text
    for item in data.get("sections", []):
        if not isinstance(item, dict):
            continue
        heading = re.sub(r"^#+\s*", "", str(item.get("heading", ""))).strip().lower()
        clean = by_line.get(heading) or next((c for c in bodies if c.lower() in heading), None)
        body = repair_tables(normalise_citations(str(item.get("body", "")))).strip()
        if not clean or len(body) < len(bodies[clean][1].strip()):
            continue  # unknown section, or the rewrite is shorter: keep the original
        line, old = bodies[clean]
        changed = changed.replace(f"## {line}{old}", f"## {line}\n{body}\n\n", 1)
    return changed if changed != text else None


def _normalise_issues(raw: list[Any], prefix: str) -> list[dict[str, Any]]:
    issues = []
    for i, item in enumerate(raw or [], 1):
        if not isinstance(item, dict):
            continue
        fix = item.get("fix") if isinstance(item.get("fix"), dict) else {}
        fix_type = fix.get("type") if fix.get("type") in ("replace", "insert_after", "none") else "none"
        issues.append({
            "id": f"{prefix}{i}",
            "severity": item.get("severity") if item.get("severity") in SEVERITIES else "medium",
            "category": str(item.get("category") or "general"),
            "location": str(item.get("location") or ""),
            "excerpt": str(item.get("excerpt") or ""),
            "problem": str(item.get("problem") or ""),
            "suggestion": str(item.get("suggestion") or ""),
            "fix": {"type": fix_type, "text": str(fix.get("text") or "") if fix_type != "none" else ""},
            "status": "open",
        })
    issues.sort(key=lambda x: SEVERITIES.index(x["severity"]))
    return issues


def _qc_facts(lesson: dict[str, Any]) -> None:
    data = llm.complete_json(prompts.FACTS_SYSTEM, prompts.facts_prompt(lesson), model=settings.qc_model, temperature=0.1)
    claims = [
        {
            "claim": str(c.get("claim", "")),
            "verdict": c.get("verdict") if c.get("verdict") in VERDICTS else "unsupported",
            "sources": [str(s) for s in (c.get("sources") or [])],
            "note": str(c.get("note") or ""),
        }
        for c in data.get("claims", []) if isinstance(c, dict)
    ]
    sound = sum(1 for c in claims if c["verdict"] in ("supported", "well_established"))
    report = {
        "summary": str(data.get("summary", "")),
        "score": round(100 * sound / len(claims)) if claims else None,
        "claims": claims,
        "source_review": [s for s in data.get("source_review", []) if isinstance(s, dict)],
        "gaps": [str(g) for g in data.get("gaps", [])],
        "issues": _normalise_issues(data.get("issues", []), "F"),
        "checks": checks.fact_checks(lesson["content"], lesson["research"] or {}),
        "content_hash": content_hash(lesson["content"]),
        "ran_at": time.time(),
        "model": f"{settings.llm_provider}/{settings.qc_model}",
    }
    db.update_lesson(lesson["id"], qc_facts=report)


def _qc_teaching(lesson: dict[str, Any]) -> None:
    timing = estimate(lesson["content"])
    data = llm.complete_json(
        prompts.TEACHING_SYSTEM, prompts.teaching_prompt(lesson, timing), model=settings.qc_model, temperature=0.2
    )
    rubric = []
    for r in data.get("rubric", []):
        if isinstance(r, dict):
            try:
                score = max(1, min(5, int(round(float(r.get("score", 0))))))
            except (TypeError, ValueError):
                continue
            rubric.append({"dimension": str(r.get("dimension", "")), "score": score, "reason": str(r.get("reason", ""))})
    coverage = [
        {
            "component": str(c.get("component", "")),
            "coverage": c.get("coverage") if c.get("coverage") in ("full", "partial", "missing") else "partial",
            "where": str(c.get("where") or ""),
            "practiced": bool(c.get("practiced")),
            "note": str(c.get("note") or ""),
        }
        for c in data.get("coverage", []) if isinstance(c, dict)
    ]
    report = {
        "summary": str(data.get("summary", "")),
        "score": round(sum(r["score"] for r in rubric) / len(rubric), 1) if rubric else None,
        "coverage": coverage,
        "rubric": rubric,
        "strengths": [str(s) for s in data.get("strengths", [])],
        "issues": _normalise_issues(data.get("issues", []), "T"),
        "checks": checks.teaching_checks(lesson["content"], lesson["objective"]),
        "content_hash": content_hash(lesson["content"]),
        "ran_at": time.time(),
        "model": f"{settings.llm_provider}/{settings.qc_model}",
    }
    db.update_lesson(lesson["id"], qc_teaching=report)


# ---------------------------------------------------------------- applying QC recommendations

class FixError(RuntimeError):
    pass


def _find_issue(lesson: dict[str, Any], layer: str, issue_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    report = lesson.get(layer)
    if not report:
        raise FixError("This review has not been run yet.")
    for issue in report["issues"]:
        if issue["id"] == issue_id:
            return report, issue
    raise FixError("That recommendation no longer exists. The review may have been re-run.")


def set_issue_status(lesson_id: str, layer: str, issue_id: str, status: str) -> None:
    lesson = db.get_lesson(lesson_id)
    if lesson is None:
        raise FixError("Lesson not found.")
    report, issue = _find_issue(lesson, layer, issue_id)
    issue["status"] = status
    db.update_lesson(lesson_id, **{layer: report})


def apply_issue(lesson_id: str, layer: str, issue_id: str, use_ai: bool) -> None:
    lesson = db.get_lesson(lesson_id)
    if lesson is None:
        raise FixError("Lesson not found.")
    report, issue = _find_issue(lesson, layer, issue_id)
    content = lesson["content"]
    if use_ai:
        revised = llm.complete(prompts.REVISE_SYSTEM, prompts.revise_prompt(content, issue), temperature=0.2)
        revised = normalise_citations(clean_markdown(revised))
        if len(revised) < len(content) * 0.6:
            raise FixError("The AI revision came back much shorter than the lesson, so it was not applied.")
        how = "with AI"
    else:
        revised = checks.apply_fix(content, issue)
        if revised is None:
            raise FixError(
                "The quoted passage is no longer in the lesson (it may have been edited), "
                "or this recommendation has no direct fix. Try 'Apply with AI' or edit by hand."
            )
        how = "directly"
    label = "Fact check" if layer == "qc_facts" else "Teaching review"
    db.save_content(lesson_id, revised, f"{label} {issue_id} applied {how}: {issue['problem'][:80]}", "qc")
    issue["status"] = "applied"
    db.update_lesson(lesson_id, **{layer: report})
