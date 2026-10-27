"""
REST endpoints for the eCourts scraper.

Routes are plain `def`, not `async def`, on purpose: the scraper uses the
blocking `requests` library, and FastAPI runs sync routes in its threadpool,
so a slow portal call (5-15 s) never blocks the event loop for other users.
An async rewrite with httpx would add complexity without a real benefit at
this scale.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..scraper import service

router = APIRouter(prefix="/api", tags=["cases"])


# ------------------------------------------------------------------ models
class CnrSearch(BaseModel):
    cnr: str = Field(..., examples=["DLND020000602007"])


class CaseNumberSearch(BaseModel):
    state_code: str = Field(..., examples=["26"])
    dist_code: str = Field(..., examples=["10"])
    court_complex: str = Field(..., description="Raw complex value from /api/meta/complexes", examples=["1260011@1,2,3,4@Y"])
    est_code: str | None = Field(None, examples=["1"])
    case_type: str = Field(..., examples=["77^1"])
    case_number: str = Field(..., examples=["233"])
    year: str = Field(..., examples=["2024"])


class CaptchaAnswer(BaseModel):
    search_id: str
    code: str


class DetailRequest(BaseModel):
    detail_ref: str


# ---------------------------------------------------------------- dropdowns
@router.get("/meta/states")
def states():
    return service.meta.states()


@router.get("/meta/districts")
def districts(state: str):
    return service.meta.districts(state)


@router.get("/meta/complexes")
def complexes(state: str, district: str):
    return service.meta.complexes(state, district)


@router.get("/meta/establishments")
def establishments(state: str, district: str, complex: str):
    return service.meta.establishments(state, district, complex)


@router.get("/meta/case-types")
def case_types(state: str, district: str, complex: str, establishment: str | None = None):
    return service.meta.case_types(state, district, complex, establishment)


# ------------------------------------------------------------------ search
@router.post("/cases/cnr")
def search_cnr(body: CnrSearch):
    """Returns `{status: "ok", type: "case", case}` or `{status: "captcha_required", ...}`."""
    return service.search_cnr(body.cnr)


@router.post("/cases/case-number")
def search_case_number(body: CaseNumberSearch):
    """Returns `{status: "ok", type: "matches", matches: [...]}` or `captcha_required`."""
    return service.search_case_number(**body.model_dump())


@router.post("/cases/captcha")
def submit_captcha(body: CaptchaAnswer):
    """Manual fallback: resume a parked search with the user's captcha answer."""
    return service.resume_with_captcha(body.search_id, body.code)


@router.post("/cases/detail")
def case_detail(body: DetailRequest):
    """Full case details for a match from the case-number search."""
    return service.case_detail(body.detail_ref)


@router.get("/cases/business")
def business(ref: str = Query(...)):
    """Daily-status details for one hearing in the case history."""
    return service.hearing_business(ref)


@router.get("/cases/order-pdf")
def order_pdf(ref: str = Query(...), download: bool = False):
    """Proxy an order/judgment PDF. Portal PDF links are session-bound temp
    files, so the browser can't link to them directly and we stream them through."""
    data, name = service.order_pdf(ref)
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{name}"', "Cache-Control": "private, max-age=600"},
    )
