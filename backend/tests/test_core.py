"""Offline tests for the parts that must be exact: matching, timing, checks, JSON parsing."""

import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["LLM_PROVIDER"] = "ollama"

import pytest  # noqa: E402

from app import checks, db, llm, pipeline, sources  # noqa: E402
from app.timing import estimate  # noqa: E402

LESSON = """# HTTP Requests and Responses
**Learning objective:** Explain GET and POST.

## Why this matters (3 min)
You use HTTP every day.

## GET and POST (12 min)
A GET request asks a server for a resource [S1]. A POST request sends data in the body [S2].

```http
GET /users HTTP/1.1
Host: example.com
```

## Activity: Sort the codes (10 min)
1. Open the browser dev tools.

## Knowledge check (5 min)
1. What does GET do?
2. What does POST do?
3. What is 404?
4. What is 500?

### Answer key
1. Reads a resource.

## Recap (15 min)
- GET reads, POST sends.

## Watch next (optional, not counted in the 45 minutes)
- [Video](https://www.youtube.com/watch?v=abcdefghijk) [V1]
"""

RESEARCH = {
    "web": [
        {"id": "S1", "url": "https://developer.mozilla.org/x", "domain": "developer.mozilla.org", "tier": "high"},
        {"id": "S2", "url": "https://medium.com/y", "domain": "medium.com", "tier": "low"},
    ],
    "books": [],
    "videos": [{"id": "V1", "video_id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk", "verified": True}],
}


def test_find_span_tolerates_whitespace_and_quotes():
    content = "Line one.\nA  GET request\nasks a “server”."
    assert checks.find_span(content, "A GET request asks a \"server\".") is not None
    assert checks.find_span(content, "not here at all") is None


def test_apply_replace_and_insert():
    issue = {"excerpt": "A GET request asks a server for a resource [S1].",
             "fix": {"type": "replace", "text": "A GET request retrieves a resource [S1]."}}
    out = checks.apply_fix(LESSON, issue)
    assert out and "retrieves a resource [S1]" in out and "asks a server" not in out

    issue = {"excerpt": "## Recap (15 min)", "fix": {"type": "insert_after", "text": "New line."}}
    out = checks.apply_fix(LESSON, issue)
    assert out and "## Recap (15 min)\n\nNew line." in out

    assert checks.apply_fix(LESSON, {"excerpt": "missing", "fix": {"type": "replace", "text": "x"}}) is None
    assert checks.apply_fix(LESSON, {"excerpt": "## Recap", "fix": {"type": "none", "text": ""}}) is None


def test_timing_reads_planned_minutes_and_skips_optional():
    t = estimate(LESSON)
    headings = [s["heading"] for s in t["sections"]]
    assert "Why this matters" in headings
    assert t["planned_total"] == 45
    assert any(s["optional"] for s in t["sections"])
    assert t["sections"][-1]["optional"] is True


def test_timing_flags_wrong_total():
    t = estimate(LESSON.replace("(15 min)", "(2 min)"))
    assert t["planned_total"] == 32
    assert any("add up to 32" in w for w in t["warnings"])


def test_fact_checks_flag_weak_source_and_unknown_ids():
    result = {c["id"]: c for c in checks.fact_checks(LESSON + "\nAlso [S9].", RESEARCH)}
    assert result["unknown_ids"]["status"] == "fail"
    assert result["weak_sources"]["status"] == "warn"
    assert result["videos"]["status"] == "pass"


def test_fact_checks_catch_unverified_video():
    bad = LESSON.replace("abcdefghijk", "zzzzzzzzzzz")
    result = {c["id"]: c for c in checks.fact_checks(bad, RESEARCH)}
    assert result["videos"]["status"] == "fail"


def test_teaching_checks_find_quiz_and_sections():
    result = {c["id"]: c for c in checks.teaching_checks(LESSON, "Explain GET and POST requests and the server response")}
    assert result["quiz"]["status"] == "pass"
    assert result["quiz_size"]["status"] == "pass"
    assert result["objective_terms"]["status"] == "pass"


def test_citation_normalisation():
    assert pipeline.normalise_citations("text [S1, S3,S4].") == "text [S1][S3][S4]."
    assert checks.cited_ids("a [S1][S2] b [S1]") == ["S1", "S2"]


def test_parse_json_handles_fences_and_prose():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Here you go: {"a": {"b": 2}} done') == {"a": {"b": 2}}
    with pytest.raises(llm.LLMError):
        llm.parse_json("no json here")


def test_source_tiers():
    assert sources.rate("https://www.rfc-editor.org/rfc/rfc9110")["tier"] == "high"
    assert sources.rate("https://en.wikipedia.org/wiki/HTTP")["tier"] == "good"
    assert sources.rate("https://cs.stanford.edu/x")["tier"] == "high"
    assert sources.rate("https://someone.medium.com/post")["tier"] == "low"
    assert sources.rate("https://random-site.io")["tier"] == "unknown"


def test_versions_keep_every_save():
    db.init_db()
    lesson = db.create_lesson("T", "Explain something useful here", "")
    db.save_content(lesson["id"], "one", "AI draft", "ai")
    db.save_content(lesson["id"], "two", "Instructor edit", "instructor")
    versions = db.list_versions(lesson["id"])
    assert [v["note"] for v in versions] == ["Instructor edit", "AI draft"]
    assert db.get_lesson(lesson["id"])["content"] == "two"


def test_interrupted_steps_become_retryable():
    db.init_db()
    lesson = db.create_lesson("T", "Explain something useful here", "")
    db.set_step(lesson["id"], "research", "running")
    db.mark_interrupted()
    step = db.get_lesson(lesson["id"])["steps"]["research"]
    assert step["status"] == "failed" and "Retry" in step["error"]


def test_repair_tables_matches_header_columns():
    broken = "| A | B |\n| :--- | :--- | :--- |\n| 1 | 2 |"
    assert pipeline.repair_tables(broken).split("\n")[1] == "| --- | --- |"
    fine = "text\n---\nmore"  # a horizontal rule is not a table
    assert pipeline.repair_tables(fine) == fine


def test_clean_markdown_splits_header_lines():
    out = pipeline.clean_markdown("# T\n**A:** x\n**B:** y\n\n## S (3 min)\nbody **bold**\n**C:** z")
    assert out.startswith("# T\n\n**A:** x\n\n**B:** y")
    assert "body **bold**\n**C:** z" in out  # only the header block changes
