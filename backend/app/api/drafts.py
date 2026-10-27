"""REST endpoints for the legal draft generator (Task 2)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ..drafts import exporters
from ..drafts.engine import DraftValidationError, generate
from ..drafts.schemas import public_schema

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftRequest(BaseModel):
    template: str
    data: dict[str, Any]


def _generate(req: DraftRequest) -> dict[str, Any]:
    try:
        return generate(req.template, req.data)
    except DraftValidationError as exc:
        # 422 with a field -> message map lets the form highlight every bad field at once.
        raise HTTPException(status_code=422, detail={"message": "Please fix the highlighted fields", "errors": exc.errors})


@router.get("/templates")
def templates():
    """All templates with their field schema and sample data (drives the dynamic form)."""
    return public_schema()


@router.post("/render")
def render(req: DraftRequest):
    draft = _generate(req)
    draft["html"] = exporters.to_html(draft, standalone=False)
    return JSONResponse(draft)


@router.post("/export/{fmt}")
def export(fmt: str, req: DraftRequest):
    draft = _generate(req)
    stem = re.sub(r"[^a-z0-9]+", "_", draft["title"].lower()).strip("_")
    if fmt == "docx":
        return Response(
            exporters.to_docx(draft),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{stem}.docx"'},
        )
    if fmt == "pdf":
        return Response(exporters.to_pdf(draft), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if fmt == "html":
        return Response(exporters.to_html(draft), media_type="text/html")
    raise HTTPException(status_code=400, detail="Format must be docx, pdf or html")
