# Demo video script (about 8 minutes)

Before recording:
- Run `./start.sh` and open http://localhost:8420.
- Delete old test lessons, or keep the Git one as your "second topic".
- With free Gemini, one lesson uses 3–4 of your 20 daily requests. Do a test run the day before and record with fresh quota.

---

**1. Intro (30 s)**
"This is Lectern. It turns a lesson title and learning objective into a researched 45-minute lesson, then checks it with two independent reviewers: one for facts, one for teaching quality."

**2. Inputs and validation (40 s)**
- Click **Research and write** with empty fields: show the inline errors.
- Click *Try an example: HTTP requests* and start the run.
- While it runs, point at the four steps: research, draft, fact check, teaching review.

**3. Research (60 s)** on the **Sources** tab
- Web pages with their reliability tier (official docs vs reference vs blog) and which ones the lesson cites.
- Open one excerpt: "the writer only sees text that was actually fetched".
- Books, and YouTube videos, each confirmed to exist before it is offered.

**4. The lesson (60 s)** on the **Lesson** tab
- Time-budget bar: planned vs measured minutes. Mention the automatic length pass (see History: "expanded to fit 45 min").
- Scroll the live preview: citation markers link to sources, the activity matches the objective's verbs, there's a knowledge check with an answer key, and videos.

**5. QC 1: facts (90 s)**
- Score, claim-by-claim verdicts with source IDs, source reliability, gaps.
- Open an *incorrect* or *misleading* finding: show the before/after, then **Apply change**.
- Automated checks: citations exist, videos verified, no stray links.

**6. QC 2: teaching (75 s)**
- Explain that it never sees the sources or QC 1's report.
- Objective coverage table: each part of the objective and whether it is practised.
- Rubric, then apply one fix. Use **Apply with AI** on one to show the fallback.

**7. Edit and history (45 s)**
- Edit a sentence and note *Unsaved changes*. Refresh the page: the edit is restored. Save with ⌘S.
- The stale-review banner appears. Click **Review the current text**.
- **History** tab: every AI draft, edit and fix, with **Restore**.

**8. Export (30 s)**
- **Preview & export**: download the .zip and open the QC reports and lesson.md. Open the printable page and use Print → Save as PDF.

**9. Second topic (40 s)**
- Show the Git lesson's QC results: the citation mismatches QC 1 found and the merge-conflict instructions QC 2 found.

**10. Tech and decisions (60 s)**
- FastAPI + SQLite backend, React + TypeScript frontend, Gemini (switchable to OpenAI or a local Ollama model).
- Why: real sources with citations; fixed reliability tiers; measured timing; independent reviewers; fixes that apply without AI calls; every version kept.
- Error handling: retry per step, provider fallbacks, nothing lost on failure.
