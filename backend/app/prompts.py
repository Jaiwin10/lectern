"""Prompts for the writer and the two independent reviewers."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_AUDIENCE = "First-year engineering students who are new to the topic"


def source_pack(research: dict[str, Any], chars_each: int = 3000) -> str:
    blocks = []
    for s in research.get("web", []):
        blocks.append(
            f"[{s['id']}] {s['title']}\nURL: {s['url']}\nPublisher type: {s['tier_label']}\n"
            f"Excerpt:\n\"\"\"\n{s['content'][:chars_each]}\n\"\"\""
        )
    for b in research.get("books", []):
        meta = ", ".join(x for x in [", ".join(b.get("authors", [])), b.get("publisher", ""), b.get("year", "")] if x)
        desc = b.get("description") or "(no description available)"
        blocks.append(f"[{b['id']}] BOOK: {b['title']} ({meta})\nURL: {b['url']}\nPublisher description:\n\"\"\"\n{desc[:900]}\n\"\"\"")
    return "\n\n".join(blocks)


def video_pack(research: dict[str, Any]) -> str:
    lines = []
    for v in research.get("videos", []):
        dur = f", {round(v['duration_sec'] / 60)} min" if v.get("duration_sec") else ""
        lines.append(f"[{v['id']}] \"{v['title']}\" by {v.get('channel') or 'unknown'}{dur}\n     {v['url']}")
    return "\n".join(lines) or "(no verified videos were found; omit the Watch next section)"


# ---------------------------------------------------------------- writer

WRITER_SYSTEM = """You are an experienced instructional designer and subject-matter expert. You write
lessons that a learner can finish in exactly 45 minutes on their own, or that an instructor can
teach from directly.

How you write:
- Plain, direct, warm. Second person ("you"). Short paragraphs of 2 to 4 sentences.
- Define each technical term the first time you use it.
- Show, then tell: every concept gets a concrete example (code, a request/response, a worked case).
- Use a table when comparing three or more things.
- No filler openings ("In today's world…", "Have you ever wondered…"), no hype, no emojis,
  no exclamation marks. Never say "delve", "dive into", "crucial", "landscape" or "unlock".
- Accuracy over flourish. If a source does not support a detail and you are not certain of it,
  leave it out."""

WRITER_PROMPT = """Write a lesson in Markdown.

LESSON TITLE: {title}
LEARNING OBJECTIVE: {objective}
AUDIENCE: {audience}

RESEARCH SOURCES (cite these by ID):
{sources}

VERIFIED YOUTUBE VIDEOS (use only these, exact URLs):
{videos}

REQUIRED STRUCTURE. Use exactly these heading levels. Every ## heading ends with its planned
time like "(5 min)". The planned times of all sections except "Watch next" must add up to
exactly 45.

# {title}
**Learning objective:** <restate the objective>
**Time:** 45 minutes · **Format:** self-paced or instructor-led
**Before you start:** <one line on prerequisites>

## Why this matters (3 min)
A concrete, realistic situation where the learner needs this. No rhetorical questions.

## <Concept sections> (2 to 4 sections, about 20 min in total)
One section per part of the learning objective. Name each heading after the idea it teaches.
Each concept section is 550 to 750 words: explain the idea, give at least two concrete
examples (fenced code blocks, request/response pairs or tables), walk through what each
example shows, and point out one common misconception or mistake.

## In practice (5 min)
One realistic, end-to-end worked example that combines the concepts, about 350 words,
with the actual code, commands or messages shown.

## Activity: <name> (8 min)
A hands-on task the learner can do with a laptop or on paper. Numbered steps, what they should
observe, and how they can check they got it right. The task must make them DO what the
objective says (for example: if the objective says "distinguish", they must sort or classify).

## Knowledge check (5 min)
5 or 6 numbered questions that test the objective: mix multiple-choice (options a–d) with
short scenario questions. Then a "### Answer key" sub-heading with each answer and a
one-sentence reason.

## Recap (2 min)
3 to 5 bullets that restate the objective in the learner's terms.

## Watch next (optional, not counted in the 45 minutes)
2 or 3 videos from the list above as "- [Title](url) by Channel: one line on why to watch it [V#]".

CITATIONS:
- After each sentence that states a fact taken from the sources, add the ID in square
  brackets, e.g. "POST requests carry data in the request body [S2]." Use one bracket per ID:
  [S1][S3], not [S1, S3].
- Use only the IDs listed above. Never invent sources, URLs, statistics or quotes.
- Do not write a references list; the tool adds it.

LENGTH: about 2,800 to 3,300 words in total. The tool measures this: at a study pace of
130 words per minute plus time to work through examples, that fills the concept and practice
sections, and the activity and knowledge check fill the rest of the 45 minutes. A lesson
under 2,500 words is too short for 45 minutes.

You may add at most two short instructor tips as blockquotes starting with "> **Instructor note:**".

Return only the Markdown lesson, with no preamble and no code fence around the whole lesson."""


# ---------------------------------------------------------------- length pass

EXPAND_PROMPT = """You wrote the lesson below. The tool measured it at about {estimated:.0f} minutes against a
45-minute budget (study pace 130 words per minute, plus time for each example). Rewrite ONLY the
sections listed, so each one has enough material for its planned time.

LESSON TITLE: {title}
LEARNING OBJECTIVE: {objective}

SECTIONS TO EXPAND (current text included):
{sections}

How to expand each section:
- Keep what is there and add depth: another worked example in a code block or table, a
  walk-through of what an example shows, a common mistake and how to spot it, or an edge case.
- Reach the target word count given for each section. Do not pad or repeat yourself.
- Cite the sources below the same way ([S1]). Add nothing the sources or standard knowledge
  do not support. Do not add new ## headings.

SOURCES:
{sources}

FULL LESSON FOR CONTEXT (do not return it):
<<<LESSON
{lesson}
LESSON>>>

Return JSON only: {{"sections": [{{"heading": "<the exact ## heading line>", "body": "<new Markdown body without the heading>"}}]}}"""


def thin_sections(timing: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        s for s in timing["sections"]
        if s["kind"] == "reading" and not s["optional"] and s["planned"] and s["reading"] < s["planned"] * 0.8
    ]


def expand_prompt(lesson: dict[str, Any], content: str, timing: dict[str, Any], bodies: dict[str, tuple[str, str]]) -> str:
    blocks = []
    for s in thin_sections(timing):
        heading_line, body = bodies[s["heading"]]
        target = int(s["planned"] * 115)
        blocks.append(
            f"### {heading_line}\nPlanned {s['planned']:g} min, now about {s['words']} words. "
            f"Target: about {target} words.\n<<<\n{body.strip()}\n>>>"
        )
    return EXPAND_PROMPT.format(
        estimated=timing["estimated_total"],
        title=lesson["title"],
        objective=lesson["objective"],
        sections="\n\n".join(blocks),
        sources=source_pack(lesson["research"]),
        lesson=content,
    )


# ---------------------------------------------------------------- QC layer 1

FACTS_SYSTEM = """You are a meticulous technical fact-checker. You did not write this lesson and you
have no stake in it. Be skeptical: a claim is "supported" only if a provided source excerpt
actually says it. You judge facts and sources only, not teaching style."""

ISSUE_RULES = """For each issue, "excerpt" MUST be copied character-for-character from the lesson
(one sentence up to one short paragraph, keep the Markdown and any [S#] tags exactly), because
the tool finds it by exact match. Write the "fix" so it can be applied without further editing:
- "replace": "text" is a drop-in replacement for the excerpt, in the same Markdown style.
- "insert_after": "text" is new Markdown to insert after the excerpt (excerpt = the anchor).
- "none": only when the problem cannot be fixed by a local edit; then "text" is "".
Keep fixes small and specific. Never invent sources; reuse existing [S#] IDs where they apply."""

FACTS_PROMPT = """Audit the lesson below for factual accuracy and source quality.

LESSON TITLE: {title}
LEARNING OBJECTIVE: {objective}

SOURCES THE LESSON WAS WRITTEN FROM:
{sources}

LESSON:
<<<LESSON
{lesson}
LESSON>>>

Do the following:
1. CLAIMS. Pick the 10 to 15 most important factual claims MADE IN THE LESSON (definitions,
   rules, numbers, behaviour, comparisons, and the answers in the answer key). Only judge
   statements that appear in the lesson text; never list a fact that appears only in the
   sources. Judge each claim exactly as worded, including qualifiers such as "always",
   "never", "hidden", "secure" or "only": a claim that is right in spirit but wrong as worded
   is "misleading". Give each a verdict:
   - "supported": a source excerpt above states it (list the IDs).
   - "well_established": no excerpt states it, but it is standard, correct knowledge in the field
     exactly as worded.
   - "unsupported": you cannot confirm it from the sources and it is not standard knowledge.
   - "misleading": technically true but likely to give learners the wrong idea.
   - "incorrect": wrong. Give the correct statement in "note".
   Also flag a cited claim whose cited source does not say it (citation mismatch) as "unsupported".
2. SOURCES. For each source ID, rate relevance (high/medium/low) and reliability
   (high/medium/low) with a short reason (publisher, how authoritative it is, how current).
3. GAPS. List inconsistencies inside the lesson, outdated statements, over-generalisations,
   and important facts the objective needs that the lesson leaves out or gets vague about.
4. ISSUES. Turn every problem into an issue with a ready-to-apply fix.
{issue_rules}

Return JSON only, exactly in this shape:
{{
  "summary": "2-3 sentences: overall factual reliability and the most important problems",
  "claims": [{{"claim": "...", "verdict": "supported|well_established|unsupported|misleading|incorrect", "sources": ["S1"], "note": "..."}}],
  "source_review": [{{"source_id": "S1", "relevance": "high|medium|low", "reliability": "high|medium|low", "note": "..."}}],
  "gaps": ["..."],
  "issues": [{{"severity": "high|medium|low", "category": "accuracy|citation|source|gap|consistency", "location": "section heading", "excerpt": "...", "problem": "...", "suggestion": "...", "fix": {{"type": "replace|insert_after|none", "text": "..."}}}}]
}}"""


# ---------------------------------------------------------------- QC layer 2

TEACHING_SYSTEM = """You are a senior instructional designer reviewing a colleague's lesson before it
goes to learners. You have not seen the research behind it and you do not judge factual accuracy;
a separate fact-checker does that. You judge whether this lesson will get the stated audience to
the learning objective in 45 minutes. Be concrete and constructive, never generic."""

TEACHING_PROMPT = """Review the teaching quality of this lesson.

LESSON TITLE: {title}
LEARNING OBJECTIVE: {objective}
AUDIENCE: {audience}

TIMING MEASURED BY THE TOOL (150 words/min reading; activities take their planned time):
{timing}

LESSON:
<<<LESSON
{lesson}
LESSON>>>

Do the following:
1. OBJECTIVE COVERAGE. Split the objective into its parts: each action verb with its concept
   (e.g. "explain GET", "distinguish 4xx from 5xx"). For each part say whether the lesson
   teaches it fully, partially or not at all, where, and whether the activity or knowledge
   check makes the learner actually practise that verb.
2. RUBRIC. Score 1 to 5 (5 = ready to teach as is) with a one-sentence reason for:
   objective alignment, clarity, structure and flow, examples, practical application,
   assessment quality, engagement, time fit.
3. STRENGTHS. 2 or 3 specific things that work well.
4. ISSUES. Missing or weak explanations, examples, practice or assessment; unclear wording;
   jargon used before it is defined; a structure that breaks the flow; timing problems.
{issue_rules}

Return JSON only, exactly in this shape:
{{
  "summary": "2-3 sentences: is this ready to teach, and what most needs to change",
  "coverage": [{{"component": "...", "coverage": "full|partial|missing", "where": "section heading", "practiced": true, "note": "..."}}],
  "rubric": [{{"dimension": "Objective alignment", "score": 4, "reason": "..."}}],
  "strengths": ["..."],
  "issues": [{{"severity": "high|medium|low", "category": "alignment|clarity|structure|example|practice|assessment|timing", "location": "section heading", "excerpt": "...", "problem": "...", "suggestion": "...", "fix": {{"type": "replace|insert_after|none", "text": "..."}}}}]
}}"""


# ---------------------------------------------------------------- AI-assisted fix

REVISE_SYSTEM = """You are an editor making one requested change to a lesson. Change as little as
possible, keep everything else exactly as it is, keep all [S#]/[B#]/[V#] citations, and keep the
"(N min)" times on the headings."""

REVISE_PROMPT = """Make this change to the lesson.

PROBLEM: {problem}
SUGGESTED CHANGE: {suggestion}
WHERE: {location}
{excerpt_line}

LESSON:
<<<LESSON
{lesson}
LESSON>>>

Return the complete revised lesson in Markdown only, with no commentary and no code fence."""


def writer_prompt(lesson: dict[str, Any]) -> str:
    research = lesson["research"]
    return WRITER_PROMPT.format(
        title=lesson["title"],
        objective=lesson["objective"],
        audience=lesson["audience"] or DEFAULT_AUDIENCE,
        sources=source_pack(research),
        videos=video_pack(research),
    )


def facts_prompt(lesson: dict[str, Any]) -> str:
    return FACTS_PROMPT.format(
        title=lesson["title"],
        objective=lesson["objective"],
        sources=source_pack(lesson["research"] or {}),
        lesson=lesson["content"],
        issue_rules=ISSUE_RULES,
    )


def teaching_prompt(lesson: dict[str, Any], timing: dict[str, Any]) -> str:
    rows = [
        f"- {s['heading']}: planned {s['planned'] if s['planned'] is not None else '?'} min, "
        f"{s['words']} words, ~{s['reading']} min reading"
        + (" (optional)" if s["optional"] else "")
        for s in timing["sections"]
    ]
    rows.append(f"Total: planned {timing['planned_total']} min, estimated {timing['estimated_total']} min.")
    rows += [f"Warning: {w}" for w in timing["warnings"]]
    return TEACHING_PROMPT.format(
        title=lesson["title"],
        objective=lesson["objective"],
        audience=lesson["audience"] or DEFAULT_AUDIENCE,
        timing="\n".join(rows),
        lesson=lesson["content"],
        issue_rules=ISSUE_RULES,
    )


def revise_prompt(content: str, issue: dict[str, Any]) -> str:
    excerpt = issue.get("excerpt") or ""
    return REVISE_PROMPT.format(
        problem=issue.get("problem", ""),
        suggestion=issue.get("suggestion", "") + (
            f"\nProposed text: {issue['fix']['text']}" if (issue.get("fix") or {}).get("text") else ""
        ),
        location=issue.get("location") or "anywhere appropriate",
        excerpt_line=f"ORIGINAL PASSAGE (may have been edited since): {json.dumps(excerpt)}" if excerpt else "",
        lesson=content,
    )
