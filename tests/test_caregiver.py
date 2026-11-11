"""Tests for Milestone 2: the caregiver dashboard.

Every test starts with an empty in-memory database (see conftest.py) and uses a "pretend
browser" (client) that fills in the same forms a caregiver would. Nothing here touches the
real data/dawai.db, and nothing makes a call or sends a message.

The eleven checks that Milestone 2 requires are marked  REQUIRED 1 ... REQUIRED 11.
The rest are extra safety checks.
"""

import html
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import get_db, init_db, make_engine
from app.main import app
from app.models import (
    CallAttempt,
    Elder,
    ElderReport,
    Medicine,
    Notification,
    ReminderOccurrence,
    ScheduleItem,
)
from app.services import caregiver, forms
from app.timeutil import utcnow


# ---------------------------------------------------------------------------
# Small helpers: fill in forms the way a caregiver would
# ---------------------------------------------------------------------------

def elder_form(**changes):
    """A correct "add elder" form. Pass keyword arguments to change a field. Use None to leave one out."""
    data = {
        "name": "Ramesh Kulkarni",
        "address_as": "Dadaji",
        "phone": "+910000000001",
        "language": "hi",
        "caregiver_name": "Sunita Kulkarni",
        "consent": "on",
    }
    data.update(changes)
    return {key: value for key, value in data.items() if value is not None}


def medicine_form(**changes):
    data = {
        "name": "Demo BP tablet",
        "spoken_name": "BP wali dawa",
        "instruction_text": "Demo instruction written by the caregiver",
    }
    data.update(changes)
    return {key: value for key, value in data.items() if value is not None}


def schedule_form(for_medicine, **changes):
    data = {
        "medicine_id": str(for_medicine),
        "time_of_day": "08:30",
        "repeat_days": ["0", "1", "2", "3", "4", "5", "6"],
        "verified": "on",
        "verified_by": "Sunita Kulkarni",
    }
    data.update(changes)
    return {key: value for key, value in data.items() if value is not None}


def add_elder(client, **changes) -> int:
    """Save an elder through the form and return the new elder's number."""
    response = client.post("/elders", data=elder_form(**changes), follow_redirects=False)
    assert response.status_code == 303, response.text
    return int(response.headers["location"].split("?")[0].rsplit("/", 1)[1])


def add_medicine(client, elder_id, **changes) -> None:
    response = client.post(
        f"/elders/{elder_id}/medicines", data=medicine_form(**changes), follow_redirects=False
    )
    assert response.status_code == 303, response.text


def add_schedule(client, elder_id, for_medicine, **changes):
    return client.post(
        f"/elders/{elder_id}/schedule-items",
        data=schedule_form(for_medicine, **changes),
        follow_redirects=False,
    )


def seen(response) -> str:
    """The page text as a person reads it: HTML codes such as &#39; turned back into '."""
    return html.unescape(response.text)


def _ticked_days(page_text: str) -> list[str]:
    """Which day boxes are ticked in the page's schedule form, for example ["1", "3"]."""
    return re.findall(r'name="repeat_days" value="([0-9])"\s+checked', page_text)


def count_rows(db, model) -> int:
    db.expire_all()
    return len(db.scalars(select(model)).all())


# ---------------------------------------------------------------------------
# REQUIRED 1, 2: a fictional elder can be created and appears on the dashboard
# ---------------------------------------------------------------------------

def test_required_1_fictional_elder_can_be_created(client, db):
    response = client.post("/elders", data=elder_form(), follow_redirects=False)

    assert response.status_code == 303  # "saved, now go and look at the profile page"
    assert response.headers["location"] == "/elders/1?notice=elder_created"

    elder = db.scalars(select(Elder)).one()
    assert elder.name == "Ramesh Kulkarni"
    assert elder.address_as == "Dadaji"
    assert elder.phone == "+910000000001"
    assert elder.language == "hi"
    assert elder.caregiver_name == "Sunita Kulkarni"


def test_required_2_elder_appears_on_dashboard(client):
    add_elder(client, name="Ramesh Kulkarni", language="hi")
    add_elder(client, name="Shanta Joshi", address_as="Aaji", language="mr", phone="+910000000002")

    page = client.get("/")

    assert page.status_code == 200
    assert "Ramesh Kulkarni" in page.text
    assert "Shanta Joshi" in page.text
    assert "Dadaji" in page.text and "Aaji" in page.text
    assert "Hindi" in page.text and "Marathi" in page.text
    assert '<p class="stat-number" id="stat-elders">2</p>' in page.text
    assert 'href="/elders/1"' in page.text and 'href="/elders/2"' in page.text
    assert 'href="/elders/new"' in page.text  # the clear "add a new elder" option


def test_dashboard_when_empty_shows_zero_and_invites_first_profile(client):
    page = client.get("/")

    assert '<p class="stat-number" id="stat-elders">0</p>' in page.text
    assert '<p class="stat-number" id="stat-medicines">0</p>' in page.text
    assert '<p class="stat-number" id="stat-schedules">0</p>' in page.text
    assert "No elder profiles yet" in page.text
    assert "Add a new elder" in page.text


def test_add_elder_form_page_opens_and_warns_about_real_data(client):
    page = client.get("/elders/new")  # must not be mistaken for /elders/{id}

    assert page.status_code == 200
    assert "fictional" in page.text.lower()
    assert "Do not enter real personal information" in page.text
    for field in ("name", "address_as", "phone", "language", "caregiver_name", "consent"):
        assert f'name="{field}"' in page.text


def test_dashboard_totals_count_everything_and_split_verified_from_unverified(client):
    first = add_elder(client)
    second = add_elder(client, name="Shanta Joshi", phone="+910000000002")
    add_medicine(client, first)
    add_medicine(client, first, name="Demo sugar tablet", spoken_name="sugar wali dawa")
    add_medicine(client, second, name="Demo vitamin", spoken_name="vitamin wali dawa")
    add_schedule(client, first, 1)  # verified
    add_schedule(client, first, 2, verified=None, verified_by=None)  # unverified
    add_schedule(client, second, 3, verified=None, verified_by=None)  # unverified

    page = client.get("/")

    assert 'id="stat-elders">2<' in page.text
    assert 'id="stat-medicines">3<' in page.text
    assert 'id="stat-schedules">3<' in page.text
    assert "1 verified, 2 unverified" in page.text


# ---------------------------------------------------------------------------
# REQUIRED 3: an invalid language is rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_language", ["en", "English", "HI", "hi ", "gu", "", "hindi"])
def test_required_3_invalid_language_is_rejected(client, db, bad_language):
    # "hi " (with a space) is trimmed to "hi", so it is the one value here that is accepted.
    response = client.post("/elders", data=elder_form(language=bad_language), follow_redirects=False)

    if bad_language.strip() == "hi":
        assert response.status_code == 303
        return

    assert response.status_code == 422
    assert "Choose Hindi or Marathi." in response.text
    assert count_rows(db, Elder) == 0  # nothing was saved


def test_language_missing_from_the_form_is_rejected(client, db):
    response = client.post("/elders", data=elder_form(language=None))

    assert response.status_code == 422
    assert "Choose Hindi or Marathi." in response.text
    assert count_rows(db, Elder) == 0


def test_both_allowed_languages_are_accepted(client, db):
    add_elder(client, language="hi", phone="+910000000001")
    add_elder(client, language="mr", phone="+910000000002")

    languages = [elder.language for elder in db.scalars(select(Elder).order_by(Elder.id))]
    assert languages == ["hi", "mr"]


# ---------------------------------------------------------------------------
# REQUIRED 4: consent information is stored correctly
# ---------------------------------------------------------------------------

def test_required_4_consent_information_is_stored_correctly(client, db):
    before = utcnow()
    elder_id = add_elder(client)
    after = utcnow()

    elder = db.get(Elder, elder_id)
    assert elder.consent_given is True
    assert elder.consent_recorded_at is not None
    # The time comes from the server's clock at the moment of saving, not from the form.
    assert before - timedelta(seconds=1) <= elder.consent_recorded_at <= after + timedelta(seconds=1)


def test_consent_time_is_shown_on_the_elder_page_in_indian_time(client, db):
    elder_id = add_elder(client)
    page = client.get(f"/elders/{elder_id}")

    assert "Demonstration consent" in page.text
    assert "Given. Recorded" in page.text
    assert " IST" in page.text

    elder = db.get(Elder, elder_id)
    shown = (elder.consent_recorded_at + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %H:%M")
    assert shown in page.text


def test_without_consent_no_profile_is_saved(client, db):
    response = client.post("/elders", data=elder_form(consent=None))

    assert response.status_code == 422
    assert "Consent must be confirmed" in response.text
    assert count_rows(db, Elder) == 0


def test_a_consent_time_sent_by_the_form_is_ignored(client, db):
    """A caregiver (or a cheat) cannot choose the consent time: the server writes it."""
    response = client.post(
        "/elders",
        data=elder_form(consent_recorded_at="2001-01-01 00:00:00", consent_given="on"),
        follow_redirects=False,
    )
    assert response.status_code == 303

    elder = db.scalars(select(Elder)).one()
    assert elder.consent_recorded_at.year >= 2026


# ---------------------------------------------------------------------------
# Missing or bad elder fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field, message",
    [
        ("name", "Name is required."),
        ("address_as", "How to address them is required."),
        ("phone", "Phone number is required."),
        ("caregiver_name", "Caregiver name is required."),
    ],
)
@pytest.mark.parametrize("empty_value", [None, "", "   "])
def test_missing_required_elder_fields_are_rejected(client, db, field, message, empty_value):
    response = client.post("/elders", data=elder_form(**{field: empty_value}))

    assert response.status_code == 422
    assert message in response.text
    assert "Nothing was saved" in response.text
    assert count_rows(db, Elder) == 0


@pytest.mark.parametrize("bad_phone", ["abc", "12345", "+91 98", "0000-000x", "+", "1" * 16, "++910000000001"])
def test_bad_phone_numbers_are_rejected(client, db, bad_phone):
    response = client.post("/elders", data=elder_form(phone=bad_phone))

    assert response.status_code == 422
    assert "Enter 10 to 15 digits" in response.text
    assert count_rows(db, Elder) == 0


def test_phone_spaces_and_hyphens_are_removed_before_saving(client, db):
    add_elder(client, phone="+91 00000-00001")

    assert db.scalars(select(Elder)).one().phone == "+910000000001"


def test_a_refused_elder_form_keeps_what_was_typed(client):
    response = client.post("/elders", data=elder_form(language="en", name="Ramesh Kulkarni"))

    assert response.status_code == 422
    assert 'value="Ramesh Kulkarni"' in response.text  # the caregiver does not have to retype


def test_too_long_names_are_rejected(client, db):
    response = client.post("/elders", data=elder_form(name="A" * 101))

    assert response.status_code == 422
    assert "Name must be 100 characters or fewer." in response.text
    assert count_rows(db, Elder) == 0


def test_typed_text_cannot_inject_html_into_the_page(client):
    elder_id = add_elder(client, name="<script>alert(1)</script>")

    page = client.get(f"/elders/{elder_id}")

    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


# ---------------------------------------------------------------------------
# REQUIRED 5: a medicine is associated with an elder
# ---------------------------------------------------------------------------

def test_required_5_medicine_is_associated_with_the_elder(client, db):
    elder_id = add_elder(client)

    response = client.post(
        f"/elders/{elder_id}/medicines", data=medicine_form(), follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/elders/{elder_id}?notice=medicine_added"
    medicine = db.scalars(select(Medicine)).one()
    assert medicine.elder_id == elder_id
    assert [m.id for m in db.get(Elder, elder_id).medicines] == [medicine.id]


def test_a_medicine_belongs_only_to_the_elder_whose_page_it_was_added_on(client, db):
    first = add_elder(client)
    second = add_elder(client, name="Shanta Joshi", phone="+910000000002")
    add_medicine(client, first, name="Demo medicine for first", spoken_name="pehli dawa")
    add_medicine(client, second, name="Demo medicine for second", spoken_name="doosri dawa")

    first_page = client.get(f"/elders/{first}").text
    second_page = client.get(f"/elders/{second}").text

    assert "Demo medicine for first" in first_page
    assert "Demo medicine for second" not in first_page
    assert "Demo medicine for second" in second_page
    assert "Demo medicine for first" not in second_page


def test_medicine_text_is_saved_exactly_as_entered(client, db):
    elder_id = add_elder(client)
    name = "Demo tablet 5 mg (blue box)"
    spoken = "BP wali goli, subah"
    instruction = "Line one\n  indented line two with   spaces\nदिन में एक बार — demo text only"
    add_medicine(client, elder_id, name=name, spoken_name=spoken, instruction_text=instruction)

    medicine = db.scalars(select(Medicine)).one()

    assert medicine.name == name
    assert medicine.spoken_name == spoken
    assert medicine.instruction_text == instruction  # inner spaces, new lines and Devanagari untouched


def test_only_spaces_at_the_very_start_and_end_are_removed(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id, name="  Demo   tablet  ", spoken_name="  BP wali dawa ")

    medicine = db.scalars(select(Medicine)).one()
    assert medicine.name == "Demo   tablet"
    assert medicine.spoken_name == "BP wali dawa"


def test_instruction_is_optional_and_saved_as_empty(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id, instruction_text="")

    assert db.scalars(select(Medicine)).one().instruction_text is None

    add_medicine(client, elder_id, name="Second", spoken_name="doosri dawa", instruction_text=None)
    db.expire_all()
    assert [m.instruction_text for m in db.scalars(select(Medicine).order_by(Medicine.id))] == [None, None]


def test_the_instruction_is_shown_back_word_for_word(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id, instruction_text="Take with water, as the caregiver wrote it")

    page = client.get(f"/elders/{elder_id}")

    assert "Take with water, as the caregiver wrote it" in page.text
    assert "Caregiver-approved instruction" in page.text


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"name": ""}, "Medicine name is required."),
        ({"name": None}, "Medicine name is required."),
        ({"spoken_name": "  "}, "Spoken name is required."),
        ({"spoken_name": None}, "Spoken name is required."),
        ({"name": "M" * 101}, "Medicine name must be 100 characters or fewer."),
        ({"instruction_text": "I" * 1001}, "The instruction must be 1000 characters or fewer."),
    ],
)
def test_bad_medicine_forms_are_rejected(client, db, changes, message):
    elder_id = add_elder(client)

    response = client.post(f"/elders/{elder_id}/medicines", data=medicine_form(**changes))

    assert response.status_code == 422
    assert message in response.text
    assert count_rows(db, Medicine) == 0


def test_a_medicine_cannot_be_added_to_an_elder_that_does_not_exist(client, db):
    response = client.post("/elders/99/medicines", data=medicine_form())

    assert response.status_code == 404
    assert count_rows(db, Medicine) == 0


# ---------------------------------------------------------------------------
# REQUIRED 6: a schedule item can be created
# ---------------------------------------------------------------------------

def test_required_6_schedule_item_can_be_created(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, time_of_day="08:30", repeat_days=["0", "2", "4"])

    assert response.status_code == 303
    item = db.scalars(select(ScheduleItem)).one()
    assert item.medicine_id == 1
    assert item.time_of_day == "08:30"
    assert item.repeat_days == "0,2,4"


def test_schedule_page_shows_time_days_and_medicine(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, time_of_day="20:15", repeat_days=["0", "2", "4"])

    page = client.get(f"/elders/{elder_id}")

    assert "20:15" in page.text
    assert "Mon, Wed, Fri" in page.text
    assert "Demo BP tablet" in page.text
    assert "BP wali dawa" in page.text


def test_repeat_days_are_saved_sorted_and_without_duplicates(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, repeat_days=["4", "0", "2", "0"])

    assert db.scalars(select(ScheduleItem)).one().repeat_days == "0,2,4"


def test_all_seven_days_show_as_every_day(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1)

    assert "Every day" in client.get(f"/elders/{elder_id}").text


def test_schedule_form_is_not_offered_until_a_medicine_exists(client):
    elder_id = add_elder(client)

    page = client.get(f"/elders/{elder_id}")

    assert "Add a medicine first" in page.text
    assert 'name="medicine_id"' not in page.text


def test_schedule_form_lists_only_this_elders_medicines(client):
    first = add_elder(client)
    second = add_elder(client, name="Shanta Joshi", phone="+910000000002")
    add_medicine(client, first, name="Demo medicine for first", spoken_name="pehli dawa")
    add_medicine(client, second, name="Demo medicine for second", spoken_name="doosri dawa")

    page = client.get(f"/elders/{first}")

    assert '<option value="1"' in page.text
    assert '<option value="2"' not in page.text


def test_all_days_are_ticked_and_verified_box_is_empty_when_the_form_opens(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    page = client.get(f"/elders/{elder_id}").text

    assert page.count('name="repeat_days"') == 7
    assert _ticked_days(page) == ["0", "1", "2", "3", "4", "5", "6"]  # every day starts ticked
    assert 'id="verified" name="verified" >' in page  # the verified box starts EMPTY: a person must tick it
    assert 'value="Sunita Kulkarni"' in page  # the caregiver's name is only a suggestion in the "checked by" box


# ---------------------------------------------------------------------------
# REQUIRED 7: a verified schedule records who verified it and when
# ---------------------------------------------------------------------------

def test_required_7_verified_schedule_records_who_and_when(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    before = utcnow()
    response = add_schedule(client, elder_id, 1, verified="on", verified_by="Sunita Kulkarni")
    after = utcnow()

    assert response.headers["location"] == f"/elders/{elder_id}?notice=schedule_verified"
    item = db.scalars(select(ScheduleItem)).one()
    assert item.verified is True
    assert item.verified_by == "Sunita Kulkarni"
    assert item.verified_at is not None
    assert before - timedelta(seconds=1) <= item.verified_at <= after + timedelta(seconds=1)


def test_verified_schedule_is_displayed_with_the_name_and_an_indian_time(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified_by="Sunita Kulkarni")

    page = client.get(f"/elders/{elder_id}")
    item = db.scalars(select(ScheduleItem)).one()
    shown_time = (item.verified_at + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %H:%M")

    assert "Verified by caregiver" in page.text
    assert f"Sunita Kulkarni, {shown_time} IST" in page.text


def test_verification_time_cannot_be_chosen_by_the_form(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified_at="2001-01-01 00:00:00")

    assert db.scalars(select(ScheduleItem)).one().verified_at.year >= 2026


def test_ticking_verified_without_a_name_is_rejected(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    for missing in ("", "   ", None):
        response = add_schedule(client, elder_id, 1, verified="on", verified_by=missing)

        assert response.status_code == 422
        assert "Enter the name of the person who checked this schedule." in response.text
    assert count_rows(db, ScheduleItem) == 0


def test_a_too_long_verifier_name_is_rejected(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, verified_by="V" * 101)

    assert response.status_code == 422
    assert "The name must be 100 characters or fewer." in response.text
    assert count_rows(db, ScheduleItem) == 0


# ---------------------------------------------------------------------------
# REQUIRED 8: an unverified schedule gets no verification details
# ---------------------------------------------------------------------------

def test_required_8_unverified_schedule_has_no_verification_details(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    # The form is normally opened with the caregiver's name pre-filled in the "checked by" box.
    # The box is NOT ticked, so that name must be thrown away.
    response = add_schedule(client, elder_id, 1, verified=None, verified_by="Sunita Kulkarni")

    assert response.status_code == 303
    assert response.headers["location"] == f"/elders/{elder_id}?notice=schedule_unverified"
    item = db.scalars(select(ScheduleItem)).one()
    assert item.verified is False
    assert item.verified_by is None
    assert item.verified_at is None


def test_unverified_schedule_is_clearly_shown_as_unverified(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified=None, verified_by=None)

    page = client.get(f"/elders/{elder_id}")

    assert "UNVERIFIED" in page.text
    assert "Will not be used for reminders" in page.text
    assert "Verified by caregiver" not in page.text  # never presented as verified
    assert "row-unverified" in page.text and "row-verified" not in page.text


def test_unverified_and_verified_schedules_are_each_labelled_correctly(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, time_of_day="08:00", verified=None, verified_by=None)
    add_schedule(client, elder_id, 1, time_of_day="09:00", verified="on", verified_by="Sunita Kulkarni")

    page = client.get(f"/elders/{elder_id}").text

    assert page.count("UNVERIFIED</span>") == 1
    assert page.count("Verified by caregiver</span>") == 1
    # The earlier time is listed first, and it is the unverified one.
    assert page.index("08:00") < page.index("09:00")
    assert page.index("UNVERIFIED</span>") < page.index("Verified by caregiver</span>")


@pytest.mark.parametrize("ticked_value", ["on", "true", "1", "yes", "ON"])
def test_every_way_a_ticked_box_is_sent_counts_as_verified(client, db, ticked_value):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified=ticked_value)

    assert db.scalars(select(ScheduleItem)).one().verified is True


@pytest.mark.parametrize("unticked_value", ["off", "false", "0", "no", "", "maybe"])
def test_anything_else_never_counts_as_verified(client, db, unticked_value):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified=unticked_value)

    item = db.scalars(select(ScheduleItem)).one()
    assert item.verified is False
    assert item.verified_by is None
    assert item.verified_at is None


# ---------------------------------------------------------------------------
# REQUIRED 9: invalid times such as 25:30 and 24:00 are rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_time",
    [
        "25:30",
        "24:00",
        "29:59",
        "23:60",
        "08:60",
        "8:30",
        "0830",
        "08.30",
        "08:3",
        "08:300",
        "ab:cd",
        "-1:30",
        "08:\n30",  # a hidden new line inside the time
        "08:30pm",
        "08:30 9",
        "٠٨:٣٠",  # digits from another script
        "",
        "   ",
    ],
)
def test_required_9_invalid_times_are_rejected(client, db, bad_time):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, time_of_day=bad_time)

    assert response.status_code == 422
    assert "Nothing was saved" in response.text
    assert count_rows(db, ScheduleItem) == 0


def test_the_invalid_time_message_explains_the_allowed_range(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    page = add_schedule(client, elder_id, 1, time_of_day="25:30")

    assert "Enter the time as HH:MM between 00:00 and 23:59, for example 08:30." in page.text


def test_a_missing_time_says_time_is_required(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    page = add_schedule(client, elder_id, 1, time_of_day=None)

    assert page.status_code == 422
    assert "Time is required." in page.text


def test_spaces_and_new_lines_around_a_valid_time_are_removed_before_saving(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, time_of_day="  08:30\n")

    assert response.status_code == 303
    assert db.scalars(select(ScheduleItem)).one().time_of_day == "08:30"  # saved clean, nothing hidden


@pytest.mark.parametrize("good_time", ["00:00", "08:30", "12:00", "19:05", "23:59"])
def test_valid_times_are_accepted(client, db, good_time):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, time_of_day=good_time)

    assert response.status_code == 303
    assert db.scalars(select(ScheduleItem)).one().time_of_day == good_time


# ---------------------------------------------------------------------------
# Invalid repeat days
# ---------------------------------------------------------------------------

def test_no_day_chosen_is_rejected(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, repeat_days=[])

    assert response.status_code == 422
    assert "Choose at least one day." in response.text
    assert count_rows(db, ScheduleItem) == 0


@pytest.mark.parametrize("bad_days", [["7"], ["-1"], ["x"], ["0", "9"], ["Monday"], ["0,1"], [""], ["٣"]])
def test_days_outside_monday_to_sunday_are_rejected(client, db, bad_days):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, repeat_days=bad_days)

    assert response.status_code == 422
    assert "Choose days from Monday to Sunday only." in response.text
    assert count_rows(db, ScheduleItem) == 0


def test_the_days_chosen_stay_ticked_when_the_form_is_refused(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    page = add_schedule(client, elder_id, 1, time_of_day="25:30", repeat_days=["1", "3"])

    assert page.status_code == 422
    assert _ticked_days(page.text) == ["1", "3"]  # Tuesday and Thursday stay ticked, the rest stay empty
    assert 'id="verified" name="verified" checked>' in page.text  # the helper ticked the verified box
    assert 'value="Sunita Kulkarni"' in page.text  # and the typed name is still there


# ---------------------------------------------------------------------------
# REQUIRED 10: invalid medicine / elder relationships are rejected
# ---------------------------------------------------------------------------

def test_required_10_a_medicine_of_another_elder_is_rejected(client, db):
    first = add_elder(client)
    second = add_elder(client, name="Shanta Joshi", phone="+910000000002")
    add_medicine(client, first)  # medicine 1 belongs to the first elder

    response = add_schedule(client, second, 1)  # ... but the form is on the second elder's page

    assert response.status_code == 422
    assert "Choose one of this elder's medicines." in seen(response)  # shown even though elder 2 has no medicines yet
    assert count_rows(db, ScheduleItem) == 0


def test_required_10_a_medicine_of_another_elder_is_rejected_when_the_elder_has_own_medicines(client, db):
    first = add_elder(client)
    second = add_elder(client, name="Shanta Joshi", phone="+910000000002")
    add_medicine(client, first)  # medicine 1 -> first elder
    add_medicine(client, second, name="Demo vitamin", spoken_name="vitamin wali dawa")  # medicine 2 -> second elder

    response = add_schedule(client, second, 1)  # elder 2's page, elder 1's medicine

    assert response.status_code == 422
    assert "Choose one of this elder's medicines." in seen(response)
    assert count_rows(db, ScheduleItem) == 0


@pytest.mark.parametrize("bad_medicine_id", ["999", "0", "-1", "abc", "1.5", "1 2", "", None])
def test_required_10_a_missing_or_unknown_medicine_is_rejected(client, db, bad_medicine_id):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, elder_id, 1, medicine_id=bad_medicine_id)

    assert response.status_code == 422
    assert ("Choose a medicine." in seen(response)) or ("Choose one of this elder's medicines." in seen(response))
    assert count_rows(db, ScheduleItem) == 0


def test_required_10_a_schedule_cannot_be_added_to_an_elder_that_does_not_exist(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)

    response = add_schedule(client, 99, 1)

    assert response.status_code == 404
    assert count_rows(db, ScheduleItem) == 0


def test_required_10_the_service_itself_also_refuses_another_elders_medicine(db):
    """Even if a route forgot to check, the service function checks again (a second lock)."""
    first = caregiver.create_elder(db, forms.validate_elder_form(elder_form()).cleaned)
    second = caregiver.create_elder(
        db, forms.validate_elder_form(elder_form(name="Shanta Joshi", phone="+910000000002")).cleaned
    )
    medicine = caregiver.add_medicine(db, first, forms.validate_medicine_form(medicine_form()).cleaned)
    cleaned = {
        "medicine_id": medicine.id,
        "time_of_day": "08:30",
        "repeat_days": "0,1,2,3,4,5,6",
        "verified": False,
        "verified_by": None,
    }

    with pytest.raises(ValueError, match="does not belong to this elder"):
        caregiver.add_schedule_item(db, second, cleaned)
    with pytest.raises(ValueError, match="does not belong to this elder"):
        caregiver.add_schedule_item(db, first, {**cleaned, "medicine_id": 999})

    assert count_rows(db, ScheduleItem) == 0


def test_required_10_the_form_check_itself_refuses_another_elders_medicine():
    """The first lock: the form check only accepts medicine numbers it is told belong to this elder."""
    data = {"medicine_id": "2", "time_of_day": "08:30"}

    result = forms.validate_schedule_form(data, ["0"], {1})

    assert not result.ok
    assert result.errors["medicine_id"] == "Choose one of this elder's medicines."
    assert result.cleaned == {}
    assert forms.validate_schedule_form({**data, "medicine_id": "1"}, ["0"], {1}).ok


def test_the_service_never_attaches_verification_details_to_an_unverified_item(db):
    """The second lock: even if a caller passes a name by mistake, an unverified item stays empty."""
    elder = caregiver.create_elder(db, forms.validate_elder_form(elder_form()).cleaned)
    medicine = caregiver.add_medicine(db, elder, forms.validate_medicine_form(medicine_form()).cleaned)

    item = caregiver.add_schedule_item(
        db,
        elder,
        {
            "medicine_id": medicine.id,
            "time_of_day": "08:30",
            "repeat_days": "0",
            "verified": False,
            "verified_by": "Someone who should be ignored",
        },
    )

    db.expire_all()
    saved = db.get(ScheduleItem, item.id)
    assert saved.verified is False
    assert saved.verified_by is None
    assert saved.verified_at is None


def test_a_missing_elder_page_gives_404(client):
    assert client.get("/elders/99").status_code == 404


def test_an_elder_number_that_is_not_a_number_is_refused_not_crashed(client):
    assert client.get("/elders/abc").status_code == 422


# ---------------------------------------------------------------------------
# REQUIRED 11: profiles and schedules survive a restart
# ---------------------------------------------------------------------------

def _pretend_browser_for(database_file):
    """Open the database FILE like a freshly started server would, and return (browser, engine)."""
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    init_db(engine)  # what the real server does at startup: create missing tables, keep the data
    factory = sessionmaker(bind=engine)

    def use_this_file():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = use_this_file
    return TestClient(app), engine


def test_required_11_profiles_and_schedules_survive_a_restart(tmp_path):
    database_file = tmp_path / "restart_test.db"

    # ---- first "run" of the application: enter data through the forms ----
    browser, first_engine = _pretend_browser_for(database_file)
    try:
        elder_id = add_elder(browser, name="Ramesh Kulkarni", language="hi")
        add_medicine(browser, elder_id)
        add_medicine(browser, elder_id, name="Demo sugar tablet", spoken_name="sugar wali dawa")
        add_schedule(browser, elder_id, 1, time_of_day="08:30", verified="on", verified_by="Sunita Kulkarni")
        add_schedule(browser, elder_id, 2, time_of_day="20:15", verified=None, verified_by=None)
        verified_page_before = browser.get(f"/elders/{elder_id}").text
    finally:
        app.dependency_overrides.clear()
        first_engine.dispose()  # the "server" stops: every connection is closed

    # ---- second "run": a brand-new engine and a brand-new browser on the SAME file ----
    browser, second_engine = _pretend_browser_for(database_file)
    try:
        dashboard = browser.get("/")
        page = browser.get("/elders/1")

        assert "Ramesh Kulkarni" in dashboard.text
        assert 'id="stat-elders">1<' in dashboard.text
        assert 'id="stat-medicines">2<' in dashboard.text
        assert 'id="stat-schedules">2<' in dashboard.text
        assert "1 verified, 1 unverified" in dashboard.text

        assert page.status_code == 200
        assert "Demo BP tablet" in page.text and "Demo sugar tablet" in page.text
        assert "08:30" in page.text and "20:15" in page.text
        assert "Sunita Kulkarni" in page.text
        assert "UNVERIFIED" in page.text
        # The page is the same as before the restart, except for the one-time "saved" message.
        assert page.text == verified_page_before

        # The relationships also survived: schedule -> medicine -> elder
        session = sessionmaker(bind=second_engine)()
        try:
            items = session.scalars(select(ScheduleItem).order_by(ScheduleItem.time_of_day)).all()
            assert [item.medicine.name for item in items] == ["Demo BP tablet", "Demo sugar tablet"]
            assert {item.medicine.elder.name for item in items} == {"Ramesh Kulkarni"}
            assert items[0].verified is True and items[0].verified_by == "Sunita Kulkarni"
            assert items[0].verified_at is not None
            assert items[1].verified is False and items[1].verified_at is None
            assert session.scalars(select(Elder)).one().consent_recorded_at is not None
        finally:
            session.close()
    finally:
        app.dependency_overrides.clear()
        second_engine.dispose()


# ---------------------------------------------------------------------------
# Safety: Milestone 2 only stores what the caregiver typed. It does nothing else.
# ---------------------------------------------------------------------------

def test_the_whole_milestone_2_flow_creates_no_reminders_calls_reports_or_notifications(client, db):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1, verified="on")
    add_schedule(client, elder_id, 1, time_of_day="21:00", verified=None, verified_by=None)
    client.get("/")
    client.get(f"/elders/{elder_id}")

    for model in (ReminderOccurrence, CallAttempt, ElderReport, Notification):
        assert count_rows(db, model) == 0, model.__name__


def test_the_pages_never_describe_a_schedule_as_checked_by_the_system(client):
    elder_id = add_elder(client)
    add_medicine(client, elder_id)
    add_schedule(client, elder_id, 1)

    page = client.get(f"/elders/{elder_id}").text

    assert "Dawai Saathi does not check it" in page
    assert "only means the caregiver says" in page
    assert "Dawai Saathi does not check medicine names" in page


def test_an_unknown_notice_code_in_the_address_shows_nothing(client):
    elder_id = add_elder(client)

    page = client.get(f"/elders/{elder_id}?notice=<b>hello</b>")

    assert page.status_code == 200
    assert "hello" not in page.text
    assert 'class="notice"' not in page.text


def test_the_saved_message_appears_once_after_saving(client):
    response = client.post("/elders", data=elder_form())  # the browser follows the redirect

    assert response.status_code == 200
    assert "Elder profile saved." in response.text
    assert 'class="notice"' not in client.get("/elders/1").text  # reloading without ?notice= shows no message


# ---------------------------------------------------------------------------
# The form checks on their own (no web, no database)
# ---------------------------------------------------------------------------

def test_describe_days_examples():
    assert forms.describe_days("0,2,4") == "Mon, Wed, Fri"
    assert forms.describe_days("0,1,2,3,4,5,6") == "Every day"
    assert forms.describe_days("5,6") == "Sat, Sun"
    assert forms.describe_days("6") == "Sun"


def test_the_form_check_returns_nothing_to_save_when_something_is_wrong():
    result = forms.validate_schedule_form(
        {"medicine_id": "1", "time_of_day": "24:00", "verified": "on", "verified_by": "Sunita"},
        ["0"],
        {1},
    )

    assert not result.ok
    assert result.cleaned == {}
    assert list(result.errors) == ["time_of_day"]
    assert result.values["time_of_day"] == "24:00"  # kept so the form can show it again


def test_language_labels_match_the_languages_the_database_allows():
    assert tuple(forms.LANGUAGE_LABELS) == ("hi", "mr")
