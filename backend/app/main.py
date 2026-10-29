"""
FastAPI entry point.

    uvicorn app.main:app --reload            (from backend/)

One app serves both tasks. The two features share nothing at runtime, but
one deployable keeps hosting free and simple. Their routers live in separate
modules, so they can be split into separate services later.

If `frontend/dist` exists (the Docker image builds it), the SPA is served
from the same origin. That lets the whole project deploy as a single Render
service, with no CORS setup and no second URL to keep in sync. During local
dev the Vite server proxies /api instead.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import cases, drafts
from .scraper.errors import EcourtsError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="VakeelAI - eCourts Scraper & Legal Draft Generator",
    version="1.0.0",
    # Docs live under /api so they work behind the Vercel rewrite (only /api/* reaches FastAPI).
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    description="Task 1: eCourts district-court case scraper (CNR / case number). "
    "Task 2: rule-based legal draft generator (no LLMs).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EcourtsError)
def ecourts_error_handler(_: Request, exc: EcourtsError):
    """All scraper failures become one JSON shape the frontend can render:
    `{status: "error", error: <class>, message}` with a meaningful HTTP code."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"status": "error", "error": type(exc).__name__, "message": exc.message},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(cases.router)
app.include_router(drafts.router)

# ----------------------------------------------------------- SPA (optional)
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        # Client-side routes (/draft, /case/...) all resolve to index.html.
        file = (_DIST / path).resolve()
        # is_relative_to() blocks "../" traversal out of the build folder.
        if path and file.is_relative_to(_DIST) and file.is_file():
            return FileResponse(file)
        return FileResponse(_DIST / "index.html")
