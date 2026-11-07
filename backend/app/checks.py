"""Automated checks that run alongside each QC layer.

These don't use an LLM. They catch the mechanical problems (made-up
citations, unverified links, missing quiz, timing) so the LLM review can
spend its effort on judgement.
"""

from __future__ import annotations

import re
from typing import Any

from .research import VIDEO_ID, keywords
from .timing import estimate, split_sections

CITATION = re.compile(r"\[((?:[SBV]\d+)(?:\s*,\s*[SBV]\d+)*)\]")
URL = re.compile(r"https?://[^\s)>\]]+")
NON_FACTUAL = re.compile(
    r"introduction|why|hook|activity|exercise|practice|knowledge check|quiz|recap|summary|watch|"
    r"video|reference|answer|before you|wrap",
    re.I,
)


def _check(cid: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def cited_ids(markdown: str) -> list[str]:
    ids: list[str] = []
    for group in CITATION.findall(markdown):
        for part in re.split(r"\s*,\s*", group):
            if part not in ids:
                ids.append(part)
    return ids


# ---------------------------------------------------------------- text matching

def find_span(content: str, excerpt: str) -> tuple[int, int] | None:
    """Find `excerpt` in `content`, ignoring differences in whitespace."""
    excerpt = (excerpt or "").strip()
    if len(excerpt) < 4:
        return None
    idx = content.find(excerpt)
    if idx != -1:
        return idx, idx + len(excerpt)
    tokens = excerpt.split()
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pattern, content)
    if m:
        return m.start(), m.end()
    # Models sometimes swap straight and curly quotes.
    def norm(s: str) -> str:
        return s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    if norm(content) != content or norm(excerpt) != excerpt:
        m = re.search(r"\s+".join(re.escape(t) for t in norm(excerpt).split()), norm(content))
        if m:
            return m.start(), m.end()  # norm() keeps string length, so indices match
    return None


def apply_fix(content: str, issue: dict[str, Any]) -> str | None:
    fix = issue.get("fix") or {}
    kind, text = fix.get("type"), (fix.get("text") or "").strip("\n")
    if kind not in ("replace", "insert_after") or not text:
        return None
    span = find_span(content, issue.get("excerpt", ""))
    if span is None:
        return None
    start, end = span
    if kind == "replace":
        return content[:start] + text + content[end:]
    return content[:end] + "\n\n" + text + content[end:]


# ---------------------------------------------------------------- QC 1 checks

def fact_checks(markdown: str, research: dict[str, Any]) -> list[dict[str, str]]:
    known = {s["id"]: s for s in research.get("web", []) + research.get("books", []) + research.get("videos", [])}
    ids = cited_ids(markdown)
    checks = []

    if not ids:
        checks.append(_check("citations", "Claims cite sources", "fail", "The lesson has no [S#] citations."))
    else:
        checks.append(_check("citations", "Claims cite sources", "pass", f"{len(ids)} different sources are cited."))

    unknown = [i for i in ids if i not in known]
    checks.append(_check(
        "unknown_ids", "Citations point to real sources",
        "fail" if unknown else "pass",
        f"Cited IDs that do not exist in the research: {', '.join(unknown)}." if unknown else "Every citation matches a collected source.",
    ))

    web_ids = [s["id"] for s in research.get("web", [])]
    used_web = [i for i in ids if i in web_ids]
    checks.append(_check(
        "breadth", "Uses several sources",
        "pass" if len(used_web) >= 3 else "warn",
        f"{len(used_web)} of {len(web_ids)} web sources are cited.",
    ))

    weak = [f"{i} ({known[i]['domain']})" for i in ids if i in known and known[i].get("tier") in ("low", "unknown")]
    checks.append(_check(
        "weak_sources", "Relies on reliable sources",
        "warn" if weak else "pass",
        f"Low or unrated sources cited: {', '.join(weak)}." if weak else "No low-reliability sources are cited.",
    ))

    uncited = []
    for heading, body in split_sections(markdown):
        if NON_FACTUAL.search(heading):
            continue
        words = len(re.findall(r"\w+", re.sub(r"```.*?```", " ", body, flags=re.S)))
        if words >= 80 and not CITATION.search(body):
            uncited.append(heading)
    checks.append(_check(
        "uncited_sections", "Explanations are backed by sources",
        "warn" if uncited else "pass",
        f"Sections with no citations: {'; '.join(uncited)}." if uncited else "Every explanation section cites at least one source.",
    ))

    known_urls = {s.get("url") for s in known.values()}
    known_videos = {v["video_id"] for v in research.get("videos", []) if v.get("verified")}
    stray, bad_videos = [], []
    for url in dict.fromkeys(URL.findall(markdown)):
        url = url.rstrip(".,;")
        vid = VIDEO_ID.search(url)
        if vid and ("youtu" in url):
            if vid.group(1) not in known_videos:
                bad_videos.append(url)
        elif url not in known_urls and not url.startswith(("http://example", "https://example", "http://localhost")):
            stray.append(url)
    checks.append(_check(
        "videos", "Video links are verified",
        "fail" if bad_videos else "pass",
        f"Videos not found by research: {', '.join(bad_videos)}." if bad_videos else "Every YouTube link was confirmed to exist.",
    ))
    checks.append(_check(
        "links", "No unverified links",
        "warn" if stray else "pass",
        f"Links not from the research: {', '.join(stray[:5])}." if stray else "All links come from collected sources.",
    ))
    return checks


# ---------------------------------------------------------------- QC 2 checks

def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups) - (1 if word.endswith("e") and len(groups) > 1 else 0)
    return max(count, 1)


def reading_ease(markdown: str) -> float:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"^\s*[#>|\-*].*$", " ", text, flags=re.M)  # skip headings, tables, lists
    sentences = [s for s in re.split(r"[.!?]+\s", text) if len(s.split()) > 3]
    words = re.findall(r"[A-Za-z]+", text)
    if not sentences or not words:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    return round(206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syl / len(words)), 1)


def teaching_checks(markdown: str, objective: str) -> list[dict[str, str]]:
    checks = []
    timing = estimate(markdown)
    checks.append(_check(
        "timing", "Fits in 45 minutes",
        "pass" if timing["fits"] else "warn",
        f"Planned {timing['planned_total']:g} min, estimated {timing['estimated_total']:.0f} min."
        + (" " + " ".join(timing["warnings"]) if timing["warnings"] else ""),
    ))

    headings = [h for h, _ in split_sections(markdown)]
    joined = " | ".join(headings).lower()
    required = [
        ("activity", "Has a hands-on activity", r"activity|exercise|practice|try it|hands"),
        ("quiz", "Has a knowledge check", r"knowledge check|quiz|check your"),
        ("recap", "Ends with a recap", r"recap|summary|wrap"),
        ("videos", "Suggests videos", r"watch|video"),
    ]
    for cid, label, pattern in required:
        ok = re.search(pattern, joined) is not None
        checks.append(_check(cid, label, "pass" if ok else "fail", "Present." if ok else "Section is missing."))

    examples = len(re.findall(r"```", markdown)) // 2 + len(re.findall(r"\bexample\b", markdown, re.I))
    checks.append(_check(
        "examples", "Uses concrete examples",
        "pass" if examples >= 3 else "warn",
        f"{examples} examples or code samples found.",
    ))

    quiz_body = ""
    for heading, body in split_sections(markdown):
        if re.search(r"knowledge check|quiz|check your", heading, re.I):
            quiz_body = body
    questions = re.split(r"#+\s*answer", quiz_body, flags=re.I)[0]
    q_count = len(re.findall(r"^\s*(?:\d+[.)]|\*\*Q\d+)", questions, re.M))
    has_key = re.search(r"answer", quiz_body, re.I) is not None
    checks.append(_check(
        "quiz_size", "Knowledge check has enough questions with answers",
        "pass" if q_count >= 4 and has_key else "warn",
        f"{q_count} questions; answer key {'present' if has_key else 'missing'}.",
    ))

    lesson_text = markdown.lower()
    terms = keywords(objective)

    def stem(t: str) -> str:
        if len(t) > 4 and t.endswith("ies"):
            return t[:-3]
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            return t[:-1]
        return t

    missing = [t for t in terms if stem(t) not in lesson_text]
    checks.append(_check(
        "objective_terms", "Covers every term in the objective",
        "pass" if not missing else "warn",
        f"Not mentioned: {', '.join(missing)}." if missing else f"All {len(terms)} key terms appear in the lesson.",
    ))

    ease = reading_ease(markdown)
    level = "easy" if ease >= 60 else "standard" if ease >= 45 else "fairly hard" if ease >= 30 else "hard"
    checks.append(_check(
        "readability", "Readable for beginners",
        "pass" if ease >= 40 else "warn",
        f"Flesch reading ease {ease:.0f} ({level}). Aim for 40 or higher.",
    ))
    return checks
