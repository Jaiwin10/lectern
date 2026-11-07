"""Exports: the final lesson (Markdown and standalone HTML), references and both QC reports."""

from __future__ import annotations

import html
import io
import json
import re
import time
import zipfile
from typing import Any

import markdown as md

from .checks import cited_ids
from .timing import estimate


def _date(ts: float | None) -> str:
    return time.strftime("%d %b %Y, %H:%M", time.localtime(ts)) if ts else "n/a"


def references_md(lesson: dict[str, Any]) -> str:
    research = lesson.get("research") or {}
    ids = set(cited_ids(lesson["content"]))
    lines = ["## References", ""]
    for s in research.get("web", []):
        if s["id"] in ids:
            lines.append(f"- **[{s['id']}]** {s['title']}. *{s['domain']}*. <{s['url']}>")
    for b in research.get("books", []):
        authors = ", ".join(b.get("authors", []))
        year = f" ({b['year']})" if b.get("year") else ""
        tag = f"**[{b['id']}]** " if b["id"] in ids else ""
        lines.append(f"- {tag}{authors}{year}. *{b['title']}*. {b.get('publisher', '')}. <{b['url']}>".replace(". .", "."))
    consulted = [s for s in research.get("web", []) if s["id"] not in ids]
    if consulted:
        lines += ["", "**Also consulted**", ""]
        lines += [f"- {s['title']}. *{s['domain']}*. <{s['url']}>" for s in consulted]
    videos = research.get("videos", [])
    if videos and not re.search(r"^##\s+Watch", lesson["content"], re.M):
        lines += ["", "**Videos**", ""]
        lines += [f"- [{v['title']}]({v['url']}), {v.get('channel', '')}" for v in videos]
    return "\n".join(lines) + "\n"


def lesson_md(lesson: dict[str, Any]) -> str:
    return lesson["content"].rstrip() + "\n\n" + references_md(lesson)


def _check_lines(checks: list[dict[str, str]]) -> list[str]:
    mark = {"pass": "Pass", "warn": "Warning", "fail": "Fail"}
    return [f"| {c['label']} | {mark.get(c['status'], c['status'])} | {c['detail']} |" for c in checks]


def _issue_lines(issues: list[dict[str, Any]]) -> list[str]:
    out = []
    for i in issues:
        out += [
            f"### {i['id']} · {i['severity'].title()} · {i['category']} · {i['status']}",
            "",
            f"**Where:** {i['location'] or 'n/a'}",
            "",
            f"**Problem:** {i['problem']}",
            "",
            f"**Suggestion:** {i['suggestion']}",
        ]
        if i.get("excerpt"):
            out += ["", "**Original:**", "", "> " + i["excerpt"].replace("\n", "\n> ")]
        if i["fix"]["type"] != "none" and i["fix"]["text"]:
            label = "Replace with" if i["fix"]["type"] == "replace" else "Insert after"
            out += ["", f"**{label}:**", "", "> " + i["fix"]["text"].replace("\n", "\n> ")]
        out.append("")
    return out


def qc_facts_md(lesson: dict[str, Any]) -> str:
    r = lesson.get("qc_facts")
    if not r:
        return "# QC Layer 1: Research and factual accuracy\n\nNot run yet.\n"
    out = [
        "# QC Layer 1: Research and factual accuracy",
        "",
        f"**Lesson:** {lesson['title']}  ",
        f"**Reviewed:** {_date(r['ran_at'])} with {r['model']}  ",
        f"**Claims judged sound:** {r['score']}%" if r.get("score") is not None else "",
        "",
        "## Summary",
        "",
        r["summary"],
        "",
        "## Automated checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *_check_lines(r["checks"]),
        "",
        "## Claims",
        "",
        "| Claim | Verdict | Sources | Note |",
        "|---|---|---|---|",
    ]
    for c in r["claims"]:
        out.append(f"| {c['claim']} | {c['verdict'].replace('_', ' ')} | {', '.join(c['sources'])} | {c['note']} |")
    out += ["", "## Source review", "", "| Source | Relevance | Reliability | Note |", "|---|---|---|---|"]
    for s in r["source_review"]:
        out.append(f"| {s.get('source_id')} | {s.get('relevance')} | {s.get('reliability')} | {s.get('note', '')} |")
    if r["gaps"]:
        out += ["", "## Gaps and inconsistencies", ""] + [f"- {g}" for g in r["gaps"]]
    out += ["", "## Issues and suggested fixes", ""] + (_issue_lines(r["issues"]) or ["None."])
    return "\n".join(out) + "\n"


def qc_teaching_md(lesson: dict[str, Any]) -> str:
    r = lesson.get("qc_teaching")
    if not r:
        return "# QC Layer 2: Instructional quality\n\nNot run yet.\n"
    t = estimate(lesson["content"])
    out = [
        "# QC Layer 2: Instructional quality",
        "",
        f"**Lesson:** {lesson['title']}  ",
        f"**Objective:** {lesson['objective']}  ",
        f"**Reviewed:** {_date(r['ran_at'])} with {r['model']}  ",
        f"**Average rubric score:** {r['score']} / 5" if r.get("score") is not None else "",
        "",
        "## Summary",
        "",
        r["summary"],
        "",
        "## Objective coverage",
        "",
        "| Part of the objective | Coverage | Practised | Where | Note |",
        "|---|---|---|---|---|",
    ]
    for c in r["coverage"]:
        out.append(f"| {c['component']} | {c['coverage']} | {'yes' if c['practiced'] else 'no'} | {c['where']} | {c['note']} |")
    out += ["", "## Rubric", "", "| Dimension | Score | Reason |", "|---|---|---|"]
    out += [f"| {x['dimension']} | {x['score']}/5 | {x['reason']} |" for x in r["rubric"]]
    if r["strengths"]:
        out += ["", "## Strengths", ""] + [f"- {s}" for s in r["strengths"]]
    out += ["", "## Timing", "", "| Section | Planned | Words | Estimated |", "|---|---|---|---|"]
    for s in t["sections"]:
        planned = f"{s['planned']:g} min" if s["planned"] is not None else "n/a"
        out.append(f"| {s['heading']}{' (optional)' if s['optional'] else ''} | {planned} | {s['words']} | {s['estimated']:.0f} min |")
    out.append(f"| **Total** | **{t['planned_total']:g} min** | {t['words']} | **{t['estimated_total']:.0f} min** |")
    out += ["", "## Automated checks", "", "| Check | Result | Detail |", "|---|---|---|", *_check_lines(r["checks"])]
    out += ["", "## Issues and suggested fixes", ""] + (_issue_lines(r["issues"]) or ["None."])
    return "\n".join(out) + "\n"


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --ink:#1d1b18; --muted:#5f5a52; --rule:#e4dfd6; --paper:#fbfaf7; --accent:#2f5d50; --code:#f2efe8; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font:18px/1.65 "Source Serif 4", "Iowan Old Style", Georgia, serif; }}
  main {{ max-width:42rem; margin:0 auto; padding:3rem 1.25rem 5rem; }}
  h1 {{ font-size:2.2rem; line-height:1.15; margin:0 0 1.25rem; letter-spacing:-0.01em; }}
  h2 {{ font-size:1.35rem; margin:2.6rem 0 0.6rem; padding-top:1.2rem; border-top:1px solid var(--rule); }}
  h3 {{ font-size:1.1rem; margin:1.8rem 0 0.4rem; }}
  a {{ color:var(--accent); }}
  sup a {{ text-decoration:none; font:600 0.7em ui-sans-serif, system-ui, sans-serif; }}
  code {{ font:0.86em "IBM Plex Mono", ui-monospace, Menlo, monospace; background:var(--code); padding:0.1em 0.3em; border-radius:3px; }}
  pre {{ background:var(--code); padding:1rem 1.1rem; border-radius:6px; overflow-x:auto; line-height:1.5; }}
  pre code {{ background:none; padding:0; }}
  table {{ border-collapse:collapse; width:100%; font-size:0.92em; margin:1rem 0; }}
  th, td {{ text-align:left; padding:0.45rem 0.6rem; border-bottom:1px solid var(--rule); vertical-align:top; }}
  blockquote {{ margin:1.2rem 0; padding:0.2rem 1rem; border-left:3px solid var(--accent); color:var(--muted); }}
  .meta {{ font:14px/1.5 ui-sans-serif, system-ui, sans-serif; color:var(--muted); margin-bottom:2rem; }}
  @media print {{ body {{ background:#fff; font-size:12pt; }} main {{ padding:0; }} h2 {{ break-after:avoid; }} pre, table {{ break-inside:avoid; }} }}
</style>
</head>
<body><main>
{body}
<p class="meta">Exported from Lectern on {date}.</p>
</main></body>
</html>"""


def _link_citations(rendered: str) -> str:
    return re.sub(r"\[([SBV]\d+)\]", r'<sup><a href="#ref-\1">\1</a></sup>', rendered)


def lesson_html(lesson: dict[str, Any]) -> str:
    body = md.markdown(lesson_md(lesson), extensions=["fenced_code", "tables", "sane_lists"])
    body = _link_citations(body)
    # Give each reference list item an anchor for the superscript links.
    body = re.sub(r"<li><strong><sup><a href=\"#ref-([SBV]\d+)\">", r'<li id="ref-\1"><strong><sup><a href="#ref-\1">', body)
    return HTML_TEMPLATE.format(title=html.escape(lesson["title"]), body=body, date=_date(time.time()))


def bundle(lesson: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("lesson.md", lesson_md(lesson))
        z.writestr("lesson.html", lesson_html(lesson))
        z.writestr("references.md", f"# {lesson['title']}: references\n\n" + references_md(lesson).split("\n", 1)[1])
        z.writestr("qc1-factual-accuracy.md", qc_facts_md(lesson))
        z.writestr("qc2-instructional-quality.md", qc_teaching_md(lesson))
        z.writestr("lesson.json", json.dumps(
            {k: lesson.get(k) for k in ("id", "title", "objective", "audience", "content", "research", "qc_facts", "qc_teaching")},
            indent=2,
        ))
    return buf.getvalue()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "lesson"
