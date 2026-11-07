# Lectern: a researched lesson builder with two-layer QC

Lectern takes a **lesson title** and a **learning objective** and turns them into a 45-minute lesson. It researches real web pages, books and YouTube videos, writes the lesson with a citation on every fact, and then has the lesson checked by two independent reviewers: one for **factual accuracy** and one for **instructional quality**. The instructor can edit the lesson, apply or dismiss each recommendation, preview the result and export everything.

Built for the Kalvium AI Research Intern task.

---

## Quick start

Requirements: Python 3.11+, Node 18+, and one LLM API key. Google Gemini's free key is enough.

```bash
cp .env.example .env        # then paste your key into GEMINI_API_KEY
./start.sh                  # installs dependencies, builds the UI, starts the server
```

Open **http://localhost:8420**. Click **Try an example: HTTP requests**, then **Research and write**. A full run takes about one to two minutes.

| Setting in `.env` | Needed? | What it does |
|---|---|---|
| `GEMINI_API_KEY` (or `OPENAI_API_KEY`) | **Yes**, one of them | Writer and reviewers. Set `LLM_PROVIDER` to match. `ollama` runs fully locally. |
| `TAVILY_API_KEY` | Recommended (free tier) | Full web search. Without it, research uses MDN Web Docs and Wikipedia only. |
| `GOOGLE_API_KEY` | Optional | YouTube Data API (durations, views) and Google Books. Without it, YouTube search with oEmbed checks and Open Library are used. |
| `QC_MODEL` | Optional | A different model for the two reviewers than for the writer. |
| `LLM_REQUESTS_PER_MINUTE` | Optional | Pace requests to stay inside free-tier limits (5 for free Gemini). |

To run the tests: `cd backend && .venv/bin/python -m pytest`

To develop the frontend with hot reload: run `./start.sh`, then `cd frontend && npm run dev`. The dev server on :5173 sends API calls to :8420.

---

## How it works

```
 title + objective
        │
        ▼
 ┌─────────────┐   Tavily ─or─ MDN + Wikipedia        (web pages, rated by publisher tier)
 │ 1. Research │   Google Books ─or─ Open Library     (books)
 └─────────────┘   YouTube API ─or─ search page  ──►  oEmbed check (the video must exist)
        │
        ▼
 ┌─────────────┐   One LLM call writes the lesson from the sources, citing [S1] [B1] [V1].
 │ 2. Draft    │   If it measures under 40 min, only the thin sections are expanded (one more call).
 └─────────────┘
        │
        ├──────────────────────────────┐
        ▼                              ▼
 ┌──────────────────┐        ┌──────────────────────┐
 │ 3. QC 1: facts   │        │ 4. QC 2: teaching    │   Separate prompts and roles.
 │ sees the sources │        │ never sees sources   │   Neither sees the other's report.
 │ + 7 automated    │        │ + 9 automated checks │
 │   checks         │        │   (timing, quiz …)   │
 └──────────────────┘        └──────────────────────┘
        │                              │
        └──────────────┬───────────────┘
                       ▼
     Review · edit · apply/dismiss fixes · preview · export (.zip / .md / .html)
```

Each step stores its own result in SQLite. If a step fails, it shows the error and a **Retry this step** button, and nothing before it is lost.

### The two QC layers

| | QC 1: Research and factual accuracy | QC 2: Instructional quality |
|---|---|---|
| **Role in the prompt** | Skeptical fact-checker who did not write the lesson | Senior instructional designer reviewing a colleague's lesson |
| **Input** | Lesson + full source excerpts | Lesson + objective + measured timing (no sources) |
| **LLM judges** | 10–15 key claims, each as *supported / well established / unsupported / misleading / incorrect*, with source IDs. Also relevance and reliability of each source, and gaps and inconsistencies | Coverage of each part of the objective and whether learners *practise* it. 8-point rubric (1–5). Strengths |
| **Automated checks** | Every citation exists. Breadth of sources. Weak sources cited. Explanation sections without citations. Unverified links. YouTube links verified | Planned time adds up to 45. Measured time within 40–50. Activity, quiz and recap present. Quiz size and answer key. Every objective term covered. Readability (Flesch) |
| **Output** | Separate report with issues and ready-to-apply fixes | Separate report with issues and ready-to-apply fixes |

Each issue quotes the exact passage and proposes replacement text, so **Apply change** is a direct text replacement with no extra AI call. If the instructor has since edited that passage, **Apply with AI** makes the change with one targeted call. Every applied fix, edit and draft is saved as a version, and any version can be restored.

---

## Design decisions

- **Real research, not model memory.** The writer only sees text that was actually fetched, and must cite it by ID. This lets QC 1 check claims against evidence instead of asking the model whether its own text sounds right.
- **Source reliability uses a fixed list, not the LLM.** Publisher tiers (standards and official docs → established references → tutorials → unrated → blogs) live in `backend/app/sources.py`. Anyone can read why a source got its rating, and the result is the same on every run. QC 1 then adds its own judgement on top.
- **Videos are verified.** A video is only offered to the writer if YouTube's oEmbed endpoint confirms it exists. Videos labelled as another language are filtered out. QC 1 fails any YouTube link in the lesson that research did not verify.
- **The 45 minutes are measured, not just claimed.** `timing.py` reads each `## Section (N min)` heading and estimates real time: 130 wpm study reading, 8 s per code line, 30 s per code block or table, with activities counted at their planned time. In testing, the writer often produced lessons that measured about 35 minutes. That is why the draft step includes a length pass that rewrites only the thin sections.
- **Two independent reviewers.** Different roles, different inputs, no access to each other's output, and optionally a different model (`QC_MODEL`). This keeps the reviews from being the writer marking its own work.
- **Fixes that apply without AI.** Reviewers must quote the exact passage. The tool finds it even if whitespace or quote styles differ, and replaces it. This is fast, uses no extra AI calls, and is reproducible.
- **Low call count.** A lesson takes 3–4 LLM calls (draft, an optional length pass, QC 1, QC 2). Research uses no LLM calls. This keeps the tool usable on free API tiers.
- **Nothing is lost.** Every draft, save, applied fix and restore is a row in `versions`. Unsaved editor text is also kept in the browser and offered back after a refresh. Steps that were cut off by a server restart are marked as failed and can be retried.

## Error handling

| Situation | What happens |
|---|---|
| Empty or too-short title or objective | Checked in the form and again on the server, with a message next to the field |
| No API key | The form explains which key is missing. Nothing is queued |
| Rate limit, 5xx error or timeout from the LLM | Up to 4 attempts with backoff (respects `Retry-After`), then a readable error and **Retry** |
| Truncated, empty or non-JSON model output | Rejected with a clear message. JSON gets one automatic repair attempt |
| A research provider fails | Falls back to the next provider and records a note on the Sources tab |
| Server stopped mid-run | Interrupted steps become *failed: retry this step* on the next start |
| Unsaved edits | Warning before leaving the page. A copy is kept in the browser. QC fixes are blocked until you save, so they can't overwrite your edits |

## Project structure

```
backend/app/
  main.py        API routes, validation, serves the built UI
  pipeline.py    the four steps, retries, length pass, applying fixes
  research.py    Tavily / MDN / Wikipedia / Google Books / Open Library / YouTube
  sources.py     publisher reliability tiers
  prompts.py     writer, QC 1, QC 2 and revision prompts
  checks.py      automated QC checks and exact-passage matching
  timing.py      45-minute budget measurement
  export.py      Markdown, HTML and ZIP exports
  llm.py         Gemini / OpenAI / Ollama over plain HTTP
  db.py          SQLite: lessons and versions
backend/tests/   offline tests (matching, timing, checks, storage)
frontend/src/    React + TypeScript UI
docs/            fact-verification notes and demo script
```

## Tested topics

1. **HTTP Requests and Responses**: the sample from the brief.
2. **Git Branching and Merging**: *Create and switch between Git branches, merge a branch into main, and resolve a simple merge conflict.*

See [docs/FACT_VERIFICATION.md](docs/FACT_VERIFICATION.md) for the key facts in each lesson, checked against authoritative sources, and examples of what each QC layer caught.

## Known limitations

- Without a Tavily key, research is limited to MDN and Wikipedia. That works well for web topics and less well for others. For example, the Git lesson could not reach git-scm.com, and QC 1 correctly flagged citations whose source did not contain the cited detail.
- Reviewers are LLMs and can be wrong. Their findings are recommendations for the instructor, not automatic edits.
- Timing is an estimate based on reading speed. Instructor-led delivery will vary.

## Acknowledgements

Open-source libraries: FastAPI, Uvicorn, httpx, python-dotenv, Python-Markdown, pytest, React, React Router, react-markdown, remark-gfm, Vite, and the Source Serif 4, IBM Plex Sans and IBM Plex Mono typefaces (via Fontsource, SIL Open Font License).
Data sources: Tavily, MDN Web Docs (CC-BY-SA), Wikipedia (CC BY-SA), Google Books, Open Library, YouTube.
