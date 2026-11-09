"""Tests for the rules that the DATABASE itself enforces in Milestone 1.

The list of those rules is at the top of app/models.py. Rules that the services must
enforce (Milestones 3 and 4: for example "only verified schedule items produce reminders"
and "a report must match its occurrence") are NOT tested here, because that code does not
exist yet. The README has the full table.

Most tests follow the same pattern:
    1. try to do something the rules forbid
    2. check that the database refuses (IntegrityError)
    3. rollback: tell the session to forget the refused change
"""

from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import init_db, make_engine
from app.models import (
    CallAttempt,
    Elder,
    ElderReport,
    Medicine,
    Notification,
    ReminderOccurrence,
    ScheduleItem,
)
from app.timeutil import utcnow

EXPECTED_TABLES = {
    "elders",
    "medicines",
    "schedule_items",
    "reminder_occurrences",
    "call_attempts",
    "elder_reports",
    "notifications",
}


# --- small helpers that build valid rows, so each test shows only what it is about ---


def add_elder(db, **changes):
    values = dict(
        name="Demo Dadaji",
        address_as="Dadaji",
        phone="+910000000000",
        language="hi",
        caregiver_name="Demo Caregiver",
    )
    values.update(changes)
    elder = Elder(**values)
    db.add(elder)
    db.commit()
    return elder


def add_schedule_item(db, **changes):
    elder = add_elder(db)
    medicine = Medicine(elder_id=elder.id, name="BP tablet (fictional)", spoken_name="BP wali dawa")
    db.add(medicine)
    db.commit()
    values = dict(medicine_id=medicine.id, time_of_day="08:00")
    values.update(changes)
    item = ScheduleItem(**values)
    db.add(item)
    db.commit()
    return item


def add_occurrence(db):
    item = add_schedule_item(db)
    occurrence = ReminderOccurrence(schedule_item_id=item.id, due_date=date(2026, 11, 9), due_time="08:00")
    db.add(occurrence)
    db.commit()
    return occurrence


def add_report(db, occurrence, **changes):
    values = dict(
        occurrence_id=occurrence.id,
        report_type="REPORTED_TAKEN",
        heard_text="haan le li",
        source="simulator_text",
    )
    values.update(changes)
    report = ElderReport(**values)
    db.add(report)
    db.commit()
    return report


# --- the tests ---


def test_all_seven_tables_exist(engine):
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES


def test_init_db_can_run_twice_without_harm(engine):
    init_db(engine)
    init_db(engine)

    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES


def test_make_engine_creates_a_missing_folder(tmp_path):
    database_file = tmp_path / "brand_new_folder" / "test.db"

    file_engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    init_db(file_engine)
    file_engine.dispose()

    assert database_file.exists()


def test_foreign_keys_are_switched_on(db):
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_a_medicine_cannot_belong_to_an_elder_who_does_not_exist(db):
    db.add(Medicine(elder_id=999, name="Ghost medicine", spoken_name="ghost"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_language_must_be_hindi_or_marathi(db):
    with pytest.raises(IntegrityError):
        add_elder(db, language="en")
    db.rollback()


def test_a_verified_schedule_item_needs_who_and_when(db):
    with pytest.raises(IntegrityError):
        add_schedule_item(db, verified=True)  # nobody's name, no time
    db.rollback()


def test_a_verified_schedule_item_with_who_and_when_is_accepted(db):
    item = add_schedule_item(db, verified=True, verified_by="Demo Caregiver", verified_at=utcnow())

    assert item.verified is True


def test_schedule_times_must_look_like_hh_mm(db):
    with pytest.raises(IntegrityError):
        add_schedule_item(db, time_of_day="8am")
    db.rollback()


@pytest.mark.parametrize("time_of_day", ["00:00", "08:30", "23:59"])
def test_valid_times_of_day_are_accepted(db, time_of_day):
    item = add_schedule_item(db, time_of_day=time_of_day)

    assert item.time_of_day == time_of_day


@pytest.mark.parametrize("time_of_day", ["24:00", "25:30", "29:59"])
def test_times_of_day_after_23_59_are_rejected(db, time_of_day):
    with pytest.raises(IntegrityError):
        add_schedule_item(db, time_of_day=time_of_day)
    db.rollback()


def test_a_schedule_item_has_only_one_occurrence_per_date(db):
    occurrence = add_occurrence(db)

    # Processing the same reminder twice must not create a duplicate
    db.add(
        ReminderOccurrence(
            schedule_item_id=occurrence.schedule_item_id,
            due_date=occurrence.due_date,
            due_time="08:00",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_an_occurrence_status_must_be_a_known_value(db):
    item = add_schedule_item(db)
    db.add(ReminderOccurrence(schedule_item_id=item.id, due_date=date(2026, 11, 9), due_time="08:00", status="verified_taken"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_call_attempt_number_can_be_used_only_once_per_occurrence(db):
    occurrence = add_occurrence(db)
    db.add(CallAttempt(occurrence_id=occurrence.id, attempt_no=1))
    db.commit()

    db.add(CallAttempt(occurrence_id=occurrence.id, attempt_no=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_recording_an_unanswered_call_creates_no_report_and_changes_no_status(db):
    # The database has no hidden automation that turns a missed call into a report or a
    # status. The Milestone 3 service must also never do it: that rule is not enforced here.
    occurrence = add_occurrence(db)
    db.add(CallAttempt(occurrence_id=occurrence.id, attempt_no=1, outcome="no_answer", ended_at=utcnow()))
    db.commit()

    assert db.query(ElderReport).count() == 0
    assert occurrence.status == "scheduled"


def test_a_report_type_must_be_one_of_the_five_intents(db):
    occurrence = add_occurrence(db)

    with pytest.raises(IntegrityError):
        add_report(db, occurrence, report_type="TAKEN_MAYBE")
    db.rollback()


def test_a_report_cannot_be_edited(db):
    occurrence = add_occurrence(db)
    report = add_report(db, occurrence)

    report.report_type = "REPORTED_NOT_TAKEN"
    with pytest.raises(IntegrityError, match="append-only"):
        db.commit()
    db.rollback()

    assert db.get(ElderReport, report.id).report_type == "REPORTED_TAKEN"


def test_a_report_cannot_be_deleted(db):
    occurrence = add_occurrence(db)
    report = add_report(db, occurrence)

    db.delete(report)
    with pytest.raises(IntegrityError, match="append-only"):
        db.commit()
    db.rollback()

    assert db.query(ElderReport).count() == 1


def test_a_correction_is_a_new_row_and_the_original_survives(db):
    occurrence = add_occurrence(db)
    original = add_report(db, occurrence, report_type="REPORTED_TAKEN")

    correction = add_report(
        db,
        occurrence,
        report_type="REPORTED_NOT_TAKEN",
        heard_text="caregiver correction",
        source="caregiver_correction",
        corrects_report_id=original.id,
    )

    assert db.query(ElderReport).count() == 2
    assert correction.corrects_report_id == original.id
    assert db.get(ElderReport, original.id).report_type == "REPORTED_TAKEN"


def test_the_same_alert_cannot_be_created_twice(db):
    elder = add_elder(db)
    alert = dict(
        elder_id=elder.id,
        kind="NO_RESPONSE",
        message="No response after two attempts",
        dedupe_key="no_response:occurrence:1",
    )
    db.add(Notification(**alert))
    db.commit()

    db.add(Notification(**alert))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_new_notification_starts_as_pending_not_delivered(db):
    elder = add_elder(db)
    db.add(Notification(elder_id=elder.id, kind="HELP_REQUESTED", message="Help requested", dedupe_key="help:1"))
    db.commit()

    notification = db.query(Notification).one()

    assert notification.delivery_status == "pending"
    assert notification.delivered_at is None
