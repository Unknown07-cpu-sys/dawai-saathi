"""What the caregiver dashboard reads and writes in the database.

Routes call these functions; the functions call nothing on the web. Each "create" function
saves with one commit, so a request either saves everything or nothing.

Nothing here makes a call, creates a reminder or changes a reported status. Those
arrive in later milestones.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Elder, Medicine, ScheduleItem
from app.timeutil import utcnow


@dataclass
class ElderRow:
    """One line of the elder list on the dashboard."""

    elder: Elder
    medicine_count: int
    schedule_count: int


def dashboard_summary(db: Session) -> dict:
    """The totals shown at the top of the dashboard."""
    elder_count = db.scalar(select(func.count()).select_from(Elder))
    medicine_count = db.scalar(select(func.count()).select_from(Medicine))
    schedule_count = db.scalar(select(func.count()).select_from(ScheduleItem))
    verified_count = db.scalar(
        select(func.count()).select_from(ScheduleItem).where(ScheduleItem.verified.is_(True))
    )
    return {
        "elder_count": elder_count,
        "medicine_count": medicine_count,
        "schedule_count": schedule_count,
        "verified_count": verified_count,
        "unverified_count": schedule_count - verified_count,
    }


def elder_rows(db: Session) -> list[ElderRow]:
    """Every elder with how many medicines and schedule items they have, oldest profile first."""
    medicine_counts = dict(
        db.execute(select(Medicine.elder_id, func.count()).group_by(Medicine.elder_id)).all()
    )
    schedule_counts = dict(
        db.execute(
            select(Medicine.elder_id, func.count(ScheduleItem.id))
            .join(ScheduleItem, ScheduleItem.medicine_id == Medicine.id)
            .group_by(Medicine.elder_id)
        ).all()
    )
    elders = db.scalars(select(Elder).order_by(Elder.id)).all()
    return [
        ElderRow(elder, medicine_counts.get(elder.id, 0), schedule_counts.get(elder.id, 0))
        for elder in elders
    ]


def get_elder(db: Session, elder_id: int) -> Elder | None:
    return db.get(Elder, elder_id)


def schedule_rows(db: Session, elder: Elder) -> list[ScheduleItem]:
    """All schedule items of one elder, earliest time first."""
    return list(
        db.scalars(
            select(ScheduleItem)
            .join(Medicine, ScheduleItem.medicine_id == Medicine.id)
            .where(Medicine.elder_id == elder.id)
            .order_by(ScheduleItem.time_of_day, ScheduleItem.id)
        )
    )


def create_elder(db: Session, cleaned: dict) -> Elder:
    """Save a new elder. The consent time is the moment of saving, taken from the server clock."""
    consent_given = bool(cleaned["consent_given"])
    elder = Elder(
        name=cleaned["name"],
        address_as=cleaned["address_as"],
        phone=cleaned["phone"],
        language=cleaned["language"],
        caregiver_name=cleaned["caregiver_name"],
        consent_given=consent_given,
        consent_recorded_at=utcnow() if consent_given else None,
    )
    db.add(elder)
    db.commit()
    return elder


def add_medicine(db: Session, elder: Elder, cleaned: dict) -> Medicine:
    """Save a medicine for this elder, with the words exactly as the caregiver typed them."""
    medicine = Medicine(
        elder_id=elder.id,
        name=cleaned["name"],
        spoken_name=cleaned["spoken_name"],
        instruction_text=cleaned["instruction_text"],
    )
    db.add(medicine)
    db.commit()
    return medicine


def add_schedule_item(db: Session, elder: Elder, cleaned: dict) -> ScheduleItem:
    """Save a schedule item for one of this elder's medicines.

    Raises ValueError if the medicine does not exist or belongs to another elder.
    Verification details are filled in ONLY if the caregiver ticked "verified"; the time of
    verification comes from the server clock. An unverified item gets no details at all.
    """
    medicine = db.get(Medicine, cleaned["medicine_id"])
    if medicine is None or medicine.elder_id != elder.id:
        raise ValueError("That medicine does not belong to this elder.")

    verified = bool(cleaned["verified"])
    item = ScheduleItem(
        medicine_id=medicine.id,
        time_of_day=cleaned["time_of_day"],
        repeat_days=cleaned["repeat_days"],
        verified=verified,
        verified_by=cleaned["verified_by"] if verified else None,
        verified_at=utcnow() if verified else None,
    )
    db.add(item)
    db.commit()
    return item
