"""Check the 45-minute budget against the actual text.

Each `## Section (N min)` heading is the planned time. We then estimate how long
the section really takes a learner working alone:
  - prose at 130 words per minute (study pace for technical text, slower than
    the ~200-250 wpm of casual reading),
  - code at 8 seconds per line,
  - plus half a minute to work through each code block or table.
Activity and knowledge-check sections take their planned time, because the
learner is doing work rather than reading. The estimate is compared with the
45-minute budget in both directions: too long and too short.
"""

from __future__ import annotations

import re
from typing import Any

WPM = 130
SECONDS_PER_CODE_LINE = 8
MINUTES_PER_BLOCK = 0.5
TARGET = 45
TOLERANCE = (40, 50)

H2 = re.compile(r"^##\s+(?!#)(.+?)\s*$", re.M)
MINUTES = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?)\s*)?min(?:ute)?s?\s*\)", re.I)
OPTIONAL = re.compile(r"optional|not counted|after (the )?lesson|^watch|video|further reading|references", re.I)
ACTIVE = re.compile(r"activity|exercise|^practice|try it|hands[- ]on|knowledge check|quiz|check your|discussion|\blab\b", re.I)
CODE_BLOCK = re.compile(r"```.*?```", re.S)


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Return (heading, body) for each H2 section; text before the first H2 is 'Introduction'."""
    matches = list(H2.finditer(markdown))
    sections: list[tuple[str, str]] = []
    head = markdown[: matches[0].start()] if matches else markdown
    head = re.sub(r"^#\s+.*$", "", head, count=1, flags=re.M)
    if head.strip():
        sections.append(("Introduction", head))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections.append((m.group(1), markdown[m.end() : end]))
    return sections


def prose_words(text: str) -> int:
    text = CODE_BLOCK.sub(" ", text)
    text = re.sub(r"\[(?:[SBV]\d+(?:,\s*)?)+\]", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text))


def blocks(text: str) -> int:
    """Code blocks and tables, each of which takes a moment to work through."""
    tables = len(re.findall(r"^\s*\|?\s*:?-{3,}", text, re.M))
    return len(CODE_BLOCK.findall(text)) + tables


def code_lines(text: str) -> int:
    total = 0
    for block in CODE_BLOCK.findall(text):
        lines = [ln for ln in block.splitlines()[1:-1] if ln.strip()]
        total += len(lines)
    return total


def estimate(markdown: str) -> dict[str, Any]:
    sections = []
    for heading, body in split_sections(markdown):
        m = MINUTES.search(heading)
        planned = float(m.group(2) or m.group(1)) if m else None
        words = prose_words(body)
        code = code_lines(body)
        reading = words / WPM + code * SECONDS_PER_CODE_LINE / 60 + blocks(body) * MINUTES_PER_BLOCK
        active = bool(ACTIVE.search(heading))
        estimated = max(reading, planned or 0) if active else reading
        sections.append({
            "heading": MINUTES.sub("", heading).strip(" -–:"),
            "planned": planned,
            "words": words,
            "code_lines": code,
            "reading": round(reading, 1),
            "estimated": round(estimated, 1),
            "kind": "activity" if active else "reading",
            "optional": bool(OPTIONAL.search(heading)),
        })

    counted = [s for s in sections if not s["optional"]]
    planned_total = sum(s["planned"] or 0 for s in counted)
    estimated_total = sum(s["estimated"] for s in counted)
    warnings = []
    if planned_total and abs(planned_total - TARGET) > 1:
        warnings.append(f"The planned section times add up to {planned_total:g} min, not {TARGET}.")
    if not planned_total:
        warnings.append("No section has a planned time. Add '(N min)' to each ## heading.")
    for s in counted:
        if s["planned"] and s["reading"] > s["planned"] * 1.25 + 1:
            warnings.append(
                f"“{s['heading']}” needs about {s['reading']:.0f} min to read but is planned for {s['planned']:g} min."
            )
        elif s["planned"] and s["kind"] == "reading" and s["planned"] >= 5 and s["reading"] < s["planned"] * 0.5:
            warnings.append(
                f"“{s['heading']}” is planned for {s['planned']:g} min but has only about {s['reading']:.0f} min of material."
            )
    if estimated_total > TOLERANCE[1]:
        warnings.append(f"Estimated total is {estimated_total:.0f} min, over the {TARGET}-minute budget.")
    elif estimated_total < TOLERANCE[0]:
        warnings.append(
            f"Estimated total is {estimated_total:.0f} min, so the lesson will likely finish early. Add depth or practice."
        )
    fits = TOLERANCE[0] <= estimated_total <= TOLERANCE[1] and abs(planned_total - TARGET) <= 1
    return {
        "sections": sections,
        "planned_total": round(planned_total, 1),
        "estimated_total": round(estimated_total, 1),
        "words": sum(s["words"] for s in sections),
        "wpm": WPM,
        "target": TARGET,
        "fits": fits,
        "warnings": warnings,
    }
