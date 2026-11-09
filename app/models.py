"""The seven database tables of Dawai Saathi.

Read this file top to bottom: each class is one table, and the comments say what
a row means and which rules the database itself checks.

The big idea: THREE different things are kept in THREE different tables, so that
they are not mixed up.

    call_attempts       what the phone (or simulator) did       "we tried to call"
    elder_reports       what the senior SAID                    "they said they took it"
    reminder_occurrences  where today's reminder stands          "reported taken", "no response"...

A missed call is only a call_attempts row. Keeping the tables apart is a design
choice: it does not, by itself, stop a future bug from writing the wrong thing into
the wrong table. The services of Milestones 3 and 4 must make sure of that.

WHAT THE DATABASE ENFORCES TODAY (Milestone 1; every point has a test in tests/test_database.py)
  - foreign keys: a row cannot point to a row that does not exist
  - the allowed values of language, occurrence status, call channel, call outcome,
    report type, report source, notification kind, channel and delivery status
  - a schedule time looks like HH:MM and lies between 00:00 and 23:59
  - one occurrence per schedule item per date, and one attempt number per occurrence
  - a "verified" schedule item must have verified_by and verified_at filled in
  - elder_reports rows cannot be edited or deleted (a correction is a new row)
  - the same notification (same dedupe_key) cannot be saved twice

WHAT THE DATABASE DOES NOT ENFORCE (the services must; see the table in README.md)
  - that only verified, active schedule items produce occurrences and calls (Milestone 3)
  - at most two call attempts per occurrence (Milestone 3)
  - that a missed call never becomes a report or a "not taken" status (Milestones 3 and 4)
  - that a report is consistent: its call attempt belongs to the same occurrence, a
    correction points to a report of the same occurrence, and the occurrence status
    follows the newest report (Milestone 4)
  - that the inbound history feature only reads and never writes (Milestone 6)
  - that a notification is marked "delivered" only when it really was (Milestone 7)
"""

from datetime import date, datetime

from sqlalchemy import (
    DDL,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.timeutil import utcnow

# ---------------------------------------------------------------------------
# The allowed values of the columns that have a CHECK rule. The database refuses
# anything else in those columns. (Columns without a CHECK rule are not restricted.)
# ---------------------------------------------------------------------------
LANGUAGES = ("hi", "mr")  # Hindi, Marathi

# Where one reminder stands. "reported_*" means the senior SAID it. It is never "verified".
OCCURRENCE_STATUSES = (
    "scheduled",  # due, nothing reported yet
    "reported_taken",
    "reported_not_taken",
    "unclear",  # we could not understand the answer, even after asking again
    "no_response",  # every call attempt went unanswered
    "help_requested",  # the senior asked for help
)

CALL_CHANNELS = ("simulator", "telephone")
CALL_OUTCOMES = ("answered", "no_answer", "failed")  # empty (NULL) while the call is still going on

# What the rule engine decides the senior meant (Milestone 4)
REPORT_TYPES = (
    "REPORTED_TAKEN",
    "REPORTED_NOT_TAKEN",
    "NEEDS_CLARIFICATION",
    "HELP_REQUESTED",
    "UNCLEAR",
)
REPORT_SOURCES = ("simulator_voice", "simulator_text", "caregiver_correction")

NOTIFICATION_KINDS = ("HELP_REQUESTED", "NO_RESPONSE")
NOTIFICATION_CHANNELS = ("dashboard", "telegram")
DELIVERY_STATUSES = ("pending", "delivered", "failed")


def _one_of(column: str, allowed: tuple[str, ...]) -> str:
    """Build the text of a CHECK rule, for example:  language IN ('hi', 'mr')"""
    quoted = ", ".join(f"'{value}'" for value in allowed)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    """Every table class below inherits from this."""


class Elder(Base):
    """One senior. Demo data must be fictional."""

    __tablename__ = "elders"
    __table_args__ = (CheckConstraint(_one_of("language", LANGUAGES), name="ck_elders_language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    address_as: Mapped[str] = mapped_column(String(50))  # how the reminder greets them, e.g. "Dadaji"
    phone: Mapped[str] = mapped_column(String(20))  # a fictional number; not used for real calls yet
    language: Mapped[str] = mapped_column(String(2))  # "hi" or "mr"
    caregiver_name: Mapped[str] = mapped_column(String(100))
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)  # consent for the demonstration
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    medicines: Mapped[list["Medicine"]] = relationship(back_populates="elder")


class Medicine(Base):
    """One medicine, typed in by the caregiver.

    The app must use these words exactly as typed and never guess or change them.
    That is a rule for the services; the database does not check it.
    """

    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(primary_key=True)
    elder_id: Mapped[int] = mapped_column(ForeignKey("elders.id"))
    name: Mapped[str] = mapped_column(String(100))  # shown on the dashboard
    spoken_name: Mapped[str] = mapped_column(String(100))  # how the reminder says it, e.g. "BP wali dawa"
    instruction_text: Mapped[str | None] = mapped_column(Text)  # optional caregiver-approved note, used word for word
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    elder: Mapped["Elder"] = relationship(back_populates="medicines")
    schedule_items: Mapped[list["ScheduleItem"]] = relationship(back_populates="medicine")


class ScheduleItem(Base):
    """One medicine at one time of day, on certain days.

    Rule for the Milestone 3 reminder service: only verified, active items may produce
    reminders. The database does NOT enforce that rule. It only requires that an item
    marked "verified" says who verified it and when.
    """

    __tablename__ = "schedule_items"
    __table_args__ = (
        # Times must be HH:MM from 00:00 to 23:59. A GLOB pattern cannot say "00 to 23" in
        # one go, so the hour is checked with two patterns: 00-19, or 20-23.
        # The minutes are 00-59. GLOB must match the whole text, so "08:300" is refused too.
        CheckConstraint(
            "time_of_day GLOB '[01][0-9]:[0-5][0-9]' OR time_of_day GLOB '2[0-3]:[0-5][0-9]'",
            name="ck_schedule_items_time_format",
        ),
        # An item marked "verified" must say WHO verified it and WHEN. The database does
        # not check that the name is meaningful: the dashboard (Milestone 2) must ask for it.
        CheckConstraint(
            "verified = 0 OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_schedule_items_verified_has_who_and_when",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id"))
    time_of_day: Mapped[str] = mapped_column(String(5))  # "08:30", Indian time
    repeat_days: Mapped[str] = mapped_column(String(13), default="0,1,2,3,4,5,6")  # Monday=0 ... Sunday=6
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # "I checked this against the prescription"
    verified_by: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    medicine: Mapped["Medicine"] = relationship(back_populates="schedule_items")
    occurrences: Mapped[list["ReminderOccurrence"]] = relationship(back_populates="schedule_item")


class ReminderOccurrence(Base):
    """One reminder on one date. This is the row the dashboard shows as "today's 8:30 BP medicine"."""

    __tablename__ = "reminder_occurrences"
    __table_args__ = (
        # The same schedule item can only have ONE occurrence per date: a second row for
        # the same item and date is refused, so processing a reminder twice cannot make a duplicate.
        UniqueConstraint("schedule_item_id", "due_date", name="uq_occurrence_schedule_and_date"),
        CheckConstraint(_one_of("status", OCCURRENCE_STATUSES), name="ck_occurrences_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_item_id: Mapped[int] = mapped_column(ForeignKey("schedule_items.id"))
    due_date: Mapped[date] = mapped_column(Date)
    # Copied from the schedule item when created. The Milestone 3 service must do the copying:
    # the database checks neither the copy, the HH:MM format here, nor the item's repeat days.
    due_time: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    status_updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    schedule_item: Mapped["ScheduleItem"] = relationship(back_populates="occurrences")
    attempts: Mapped[list["CallAttempt"]] = relationship(back_populates="occurrence")
    reports: Mapped[list["ElderReport"]] = relationship(back_populates="occurrence")


class CallAttempt(Base):
    """One try to reach the senior. It records what the PHONE did, not what the senior said."""

    __tablename__ = "call_attempts"
    __table_args__ = (
        UniqueConstraint("occurrence_id", "attempt_no", name="uq_attempt_number_per_occurrence"),
        CheckConstraint("attempt_no >= 1", name="ck_attempts_number_positive"),
        CheckConstraint(_one_of("channel", CALL_CHANNELS), name="ck_attempts_channel"),
        # outcome may be empty (NULL) while the call is in progress; otherwise it must be one of these
        CheckConstraint(_one_of("outcome", CALL_OUTCOMES), name="ck_attempts_outcome"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("reminder_occurrences.id"))
    # 1 = first try, 2 = the retry. The limit of two attempts is a rule for the Milestone 3
    # service; the database only requires 1 or more, and one row per number.
    attempt_no: Mapped[int]
    channel: Mapped[str] = mapped_column(String(10), default="simulator")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    outcome: Mapped[str | None] = mapped_column(String(10))

    occurrence: Mapped["ReminderOccurrence"] = relationship(back_populates="attempts")


class ElderReport(Base):
    """One thing the senior SAID, after the rule engine classified it.

    This table is APPEND-ONLY: rows are never edited or deleted (two triggers at the
    bottom of this file make SQLite refuse). A correction is a NEW row whose
    corrects_report_id points to the row it corrects, so the original history survives.

    What the database does NOT check (the Milestone 4 report service must):
      - that call_attempt_id belongs to the same occurrence as the report
      - that corrects_report_id points to a report of the same occurrence
      - that source "caregiver_correction" goes together with corrects_report_id
      - that the occurrence status matches the newest report
    """

    __tablename__ = "elder_reports"
    __table_args__ = (
        CheckConstraint(_one_of("report_type", REPORT_TYPES), name="ck_reports_type"),
        CheckConstraint(_one_of("source", REPORT_SOURCES), name="ck_reports_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("reminder_occurrences.id"))
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id"))
    report_type: Mapped[str] = mapped_column(String(20))
    heard_text: Mapped[str] = mapped_column(Text, default="")  # the words recognised; never audio
    matched_rule: Mapped[str | None] = mapped_column(String(100))  # which rule made the decision
    source: Mapped[str] = mapped_column(String(25))
    corrects_report_id: Mapped[int | None] = mapped_column(ForeignKey("elder_reports.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    occurrence: Mapped["ReminderOccurrence"] = relationship(back_populates="reports")


class Notification(Base):
    """One alert for the caregiver (a help request, or no response after two attempts).

    delivery_status is meant to tell the truth: the app may only say "the caregiver was
    contacted" when this says "delivered", and "pending" and "failed" must be shown as such.
    The database only checks that the value is one of the three. It does not check that
    "delivered" comes with delivered_at, or that the status is set honestly: the
    Milestone 7 notification service must do that.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(_one_of("kind", NOTIFICATION_KINDS), name="ck_notifications_kind"),
        CheckConstraint(_one_of("channel", NOTIFICATION_CHANNELS), name="ck_notifications_channel"),
        CheckConstraint(_one_of("delivery_status", DELIVERY_STATUSES), name="ck_notifications_delivery"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    elder_id: Mapped[int] = mapped_column(ForeignKey("elders.id"))
    occurrence_id: Mapped[int | None] = mapped_column(ForeignKey("reminder_occurrences.id"))
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(10), default="dashboard")
    delivery_status: Mapped[str] = mapped_column(String(10), default="pending")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    # A made-up unique label such as "no_response:occurrence:7". Saving a second alert with
    # the same label is refused. (The service must build the label the same way every time.)
    dedupe_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Make elder_reports append-only. SQLite runs these two triggers automatically
# whenever someone tries to change or delete a row, and the change is refused.
# This guards against mistakes in our own code. It is not tamper-proof: anyone who
# opens the database file with another tool can drop the triggers.
# ---------------------------------------------------------------------------
_NO_UPDATE = DDL(
    "CREATE TRIGGER IF NOT EXISTS elder_reports_no_update BEFORE UPDATE ON elder_reports "
    "BEGIN SELECT RAISE(ABORT, 'elder_reports is append-only: add a correction row instead'); END"
)
_NO_DELETE = DDL(
    "CREATE TRIGGER IF NOT EXISTS elder_reports_no_delete BEFORE DELETE ON elder_reports "
    "BEGIN SELECT RAISE(ABORT, 'elder_reports is append-only: rows cannot be deleted'); END"
)
event.listen(ElderReport.__table__, "after_create", _NO_UPDATE.execute_if(dialect="sqlite"))
event.listen(ElderReport.__table__, "after_create", _NO_DELETE.execute_if(dialect="sqlite"))
