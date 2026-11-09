"""The pages people see in the browser. For now: only the home page."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Elder
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """The home page: shows that the server runs and how many elder profiles exist."""
    elder_count = db.scalar(select(func.count()).select_from(Elder))
    return templates.TemplateResponse(
        request,
        "home.html",
        {"app_name": settings.app_name, "elder_count": elder_count},
    )
