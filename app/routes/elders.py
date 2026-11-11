"""Caregiver pages: add an elder, open an elder, add a medicine, add a schedule item.

Each "add" works the same way:
    1. read the submitted form
    2. check it with app/services/forms.py
    3. if something is wrong, show the same page again with the messages (HTTP status 422)
    4. if it is fine, save it with app/services/caregiver.py and redirect to the elder's page
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Elder
from app.services import caregiver, forms
from app.templating import templates

router = APIRouter()

# The message after a save is chosen from this fixed list by a short code in the address.
# The address never carries text that a person typed, so nothing typed can appear in it.
NOTICES = {
    "elder_created": "Elder profile saved.",
    "medicine_added": "Medicine saved exactly as you entered it.",
    "schedule_verified": "Schedule saved. It is marked as checked and verified, as you confirmed.",
    "schedule_unverified": "Schedule saved as UNVERIFIED. It has not been marked as checked.",
}


def _text_fields(form) -> dict:
    """The plain-text fields of a submitted form (uploaded files are ignored)."""
    return {key: value for key, value in form.items() if isinstance(value, str)}


def _chosen_days(form) -> list[str]:
    return [value for value in form.getlist("repeat_days") if isinstance(value, str)]


def _get_elder_or_404(db: Session, elder_id: int) -> Elder:
    elder = caregiver.get_elder(db, elder_id)
    if elder is None:
        raise HTTPException(status_code=404, detail="Elder profile not found")
    return elder


def _elder_form_page(request: Request, values: dict, errors: dict, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "elder_form.html",
        {"values": values, "errors": errors, "languages": forms.LANGUAGE_LABELS},
        status_code=status_code,
    )


def _detail_page(
    request: Request,
    db: Session,
    elder: Elder,
    *,
    medicine_form: forms.FormResult | None = None,
    schedule_form: forms.FormResult | None = None,
    notice: str | None = None,
    status_code: int = 200,
):
    """The page of one elder. A form that was refused is shown again with its messages."""
    default_schedule_values = {
        "repeat_days": sorted(forms.DAY_VALUES),
        "verified": False,
        "verified_by": elder.caregiver_name,  # a suggestion only; nothing is verified unless the box is ticked
    }
    return templates.TemplateResponse(
        request,
        "elder_detail.html",
        {
            "elder": elder,
            "language_label": forms.LANGUAGE_LABELS.get(elder.language, elder.language),
            "medicines": sorted(elder.medicines, key=lambda medicine: medicine.id),
            "schedule_items": caregiver.schedule_rows(db, elder),
            "days": list(enumerate(forms.DAY_NAMES)),
            "notice": notice,
            "medicine_values": medicine_form.values if medicine_form else {},
            "medicine_errors": medicine_form.errors if medicine_form else {},
            "schedule_values": schedule_form.values if schedule_form else default_schedule_values,
            "schedule_errors": schedule_form.errors if schedule_form else {},
        },
        status_code=status_code,
    )


@router.get("/elders/new", response_class=HTMLResponse)
def new_elder_form(request: Request):
    return _elder_form_page(request, values={}, errors={})


@router.post("/elders", response_class=HTMLResponse)
async def create_elder(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    result = forms.validate_elder_form(_text_fields(form))
    if not result.ok:
        return _elder_form_page(request, result.values, result.errors, status_code=422)

    elder = caregiver.create_elder(db, result.cleaned)
    return RedirectResponse(f"/elders/{elder.id}?notice=elder_created", status_code=303)


@router.get("/elders/{elder_id}", response_class=HTMLResponse)
def show_elder(elder_id: int, request: Request, notice: str | None = None, db: Session = Depends(get_db)):
    elder = _get_elder_or_404(db, elder_id)
    return _detail_page(request, db, elder, notice=NOTICES.get(notice or ""))


@router.post("/elders/{elder_id}/medicines", response_class=HTMLResponse)
async def add_medicine(elder_id: int, request: Request, db: Session = Depends(get_db)):
    elder = _get_elder_or_404(db, elder_id)
    form = await request.form()
    result = forms.validate_medicine_form(_text_fields(form))
    if not result.ok:
        return _detail_page(request, db, elder, medicine_form=result, status_code=422)

    caregiver.add_medicine(db, elder, result.cleaned)
    return RedirectResponse(f"/elders/{elder.id}?notice=medicine_added", status_code=303)


@router.post("/elders/{elder_id}/schedule-items", response_class=HTMLResponse)
async def add_schedule_item(elder_id: int, request: Request, db: Session = Depends(get_db)):
    elder = _get_elder_or_404(db, elder_id)
    form = await request.form()
    own_medicine_ids = {medicine.id for medicine in elder.medicines}
    result = forms.validate_schedule_form(_text_fields(form), _chosen_days(form), own_medicine_ids)

    item = None
    if result.ok:
        try:
            item = caregiver.add_schedule_item(db, elder, result.cleaned)
        except ValueError:  # the service double-checks the medicine belongs to this elder
            result.errors["medicine_id"] = "Choose one of this elder's medicines."
    if item is None:
        return _detail_page(request, db, elder, schedule_form=result, status_code=422)

    notice = "schedule_verified" if item.verified else "schedule_unverified"
    return RedirectResponse(f"/elders/{elder.id}?notice={notice}", status_code=303)
