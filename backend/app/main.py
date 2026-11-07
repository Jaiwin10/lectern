"""HTTP API. Also serves the built frontend, so one process runs the whole tool."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import checks, db, export, llm, pipeline
from .config import ROOT, settings
from .timing import estimate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    db.mark_interrupted()
    yield


app = FastAPI(title="Lectern", lifespan=lifespan)

LAYERS = {"facts": "qc_facts", "teaching": "qc_teaching"}


# ---------------------------------------------------------------- helpers

def _load(lesson_id: str) -> dict[str, Any]:
    lesson = db.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(404, "Lesson not found.")
    return lesson


def _serialise(lesson: dict[str, Any]) -> dict[str, Any]:
    current = pipeline.content_hash(lesson["content"])
    for layer in LAYERS.values():
        report = lesson.get(layer)
        if not report:
            continue
        report["stale"] = report.get("content_hash") != current
        for issue in report["issues"]:
            issue["applicable"] = (
                issue["fix"]["type"] != "none" and checks.find_span(lesson["content"], issue["excerpt"]) is not None
            )
    lesson["timing"] = estimate(lesson["content"]) if lesson["content"] else None
    lesson["busy"] = pipeline.is_busy(lesson["id"])
    lesson["version_count"] = db.count_versions(lesson["id"])
    return lesson


def _layer(name: str) -> str:
    if name not in LAYERS:
        raise HTTPException(404, "Unknown review layer.")
    return LAYERS[name]


# ---------------------------------------------------------------- models

class NewLesson(BaseModel):
    title: str = ""
    objective: str = ""
    audience: str = ""


class SaveContent(BaseModel):
    content: str
    note: str = ""


class RunStep(BaseModel):
    step: str


# ---------------------------------------------------------------- routes

@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "llm": llm.describe(),
        "research": {
            "web": "Tavily" if settings.tavily_api_key else "MDN Web Docs + Wikipedia (add TAVILY_API_KEY for full web search)",
            "videos": "YouTube Data API" if settings.google_api_key else "YouTube search + oEmbed check",
            "books_provider": "Google Books" if settings.google_api_key else "Open Library",
        },
    }


@app.get("/api/lessons")
def lessons() -> list[dict[str, Any]]:
    return db.list_lessons()


@app.post("/api/lessons", status_code=201)
def create(body: NewLesson) -> dict[str, Any]:
    title, objective = body.title.strip(), body.objective.strip()
    problems = {}
    if not title:
        problems["title"] = "Enter a lesson title."
    elif len(title) < 3 or len(title) > 150:
        problems["title"] = "Keep the title between 3 and 150 characters."
    if not objective:
        problems["objective"] = "Enter a learning objective."
    elif len(objective.split()) < 4:
        problems["objective"] = "Write the objective as a full sentence, e.g. 'Explain … and distinguish …'."
    elif len(objective) > 600:
        problems["objective"] = "Keep the objective under 600 characters."
    if problems:
        raise HTTPException(422, {"message": "Please fix the highlighted fields.", "fields": problems})
    if not llm.is_configured():
        raise HTTPException(503, f"No API key is set for {settings.llm_provider}. Add it to .env and restart.")
    lesson = db.create_lesson(title, objective, body.audience.strip()[:200])
    pipeline.start(lesson["id"], list(db.STEPS))
    return _serialise(db.get_lesson(lesson["id"]))  # type: ignore[arg-type]


@app.get("/api/lessons/{lesson_id}")
def read(lesson_id: str) -> dict[str, Any]:
    return _serialise(_load(lesson_id))


@app.delete("/api/lessons/{lesson_id}", status_code=204)
def delete(lesson_id: str) -> Response:
    _load(lesson_id)
    if pipeline.is_busy(lesson_id):
        raise HTTPException(409, "Wait for the current step to finish before deleting.")
    db.delete_lesson(lesson_id)
    return Response(status_code=204)


@app.put("/api/lessons/{lesson_id}/content")
def save(lesson_id: str, body: SaveContent) -> dict[str, Any]:
    lesson = _load(lesson_id)
    if not body.content.strip():
        raise HTTPException(422, "The lesson is empty. Nothing was saved.")
    if body.content != lesson["content"]:
        db.save_content(lesson_id, body.content, body.note.strip() or "Instructor edit", "instructor")
    return _serialise(_load(lesson_id))


@app.post("/api/lessons/{lesson_id}/run")
def run(lesson_id: str, body: RunStep) -> dict[str, Any]:
    lesson = _load(lesson_id)
    if body.step not in db.STEPS:
        raise HTTPException(422, "Unknown step.")
    if not llm.is_configured():
        raise HTTPException(503, f"No API key is set for {settings.llm_provider}. Add it to .env and restart.")
    if not pipeline.start(lesson_id, pipeline.plan_for(lesson, body.step)):
        raise HTTPException(409, "A step is already running for this lesson.")
    return _serialise(_load(lesson_id))


@app.post("/api/lessons/{lesson_id}/qc/{layer}/issues/{issue_id}/{action}")
def issue_action(lesson_id: str, layer: str, issue_id: str, action: str) -> dict[str, Any]:
    field = _layer(layer)
    _load(lesson_id)
    if pipeline.is_busy(lesson_id):
        raise HTTPException(409, "Wait for the current step to finish.")
    try:
        if action == "apply":
            pipeline.apply_issue(lesson_id, field, issue_id, use_ai=False)
        elif action == "apply-ai":
            pipeline.apply_issue(lesson_id, field, issue_id, use_ai=True)
        elif action in ("dismiss", "reopen"):
            pipeline.set_issue_status(lesson_id, field, issue_id, "dismissed" if action == "dismiss" else "open")
        else:
            raise HTTPException(404, "Unknown action.")
    except (pipeline.FixError, llm.LLMError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _serialise(_load(lesson_id))


@app.get("/api/lessons/{lesson_id}/versions")
def versions(lesson_id: str) -> list[dict[str, Any]]:
    _load(lesson_id)
    return db.list_versions(lesson_id)


@app.get("/api/lessons/{lesson_id}/versions/{version_id}")
def version(lesson_id: str, version_id: int) -> dict[str, Any]:
    v = db.get_version(lesson_id, version_id)
    if v is None:
        raise HTTPException(404, "Version not found.")
    return v


@app.post("/api/lessons/{lesson_id}/versions/{version_id}/restore")
def restore(lesson_id: str, version_id: int) -> dict[str, Any]:
    _load(lesson_id)
    v = db.get_version(lesson_id, version_id)
    if v is None:
        raise HTTPException(404, "Version not found.")
    db.save_content(lesson_id, v["content"], f"Restored version {version_id}", "instructor")
    return _serialise(_load(lesson_id))


# ---------------------------------------------------------------- export

@app.get("/api/lessons/{lesson_id}/export/{kind}")
def export_file(lesson_id: str, kind: str) -> Response:
    lesson = _load(lesson_id)
    if not lesson["content"] and kind != "bundle":
        raise HTTPException(409, "There is no lesson text to export yet.")
    name = export.slug(lesson["title"])
    files = {
        "lesson.md": (lambda: export.lesson_md(lesson), "text/markdown", f"{name}.md"),
        "qc1.md": (lambda: export.qc_facts_md(lesson), "text/markdown", f"{name}-qc1-factual-accuracy.md"),
        "qc2.md": (lambda: export.qc_teaching_md(lesson), "text/markdown", f"{name}-qc2-instructional-quality.md"),
        "references.md": (lambda: export.references_md(lesson), "text/markdown", f"{name}-references.md"),
    }
    if kind == "lesson.html":
        return HTMLResponse(export.lesson_html(lesson))
    if kind == "bundle":
        return Response(
            export.bundle(lesson),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
        )
    if kind not in files:
        raise HTTPException(404, "Unknown export.")
    build, media, filename = files[kind]
    return PlainTextResponse(
        build(), media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ---------------------------------------------------------------- frontend

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = DIST / path
        if path and target.is_file() and Path(target).resolve().is_relative_to(DIST.resolve()):
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
