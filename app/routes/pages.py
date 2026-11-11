"""The pages people see in the browser. For now: the dashboard (home page)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import caregiver
from app.services.forms import LANGUAGE_LABELS
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """The caregiver dashboard: totals, the list of elders and a button to add one."""
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "summary": caregiver.dashboard_summary(db),
            "rows": caregiver.elder_rows(db),
            "language_labels": LANGUAGE_LABELS,
        },
    )
