"""Validation for the three caregiver forms: elder, medicine and schedule item.

These are plain functions: text in, a result out. They know nothing about the web or the
database, so they are easy to test. The browser's own limits (such as maxlength) are only a
convenience. THIS code is the real check, and it runs on the server for every submission.

Every function returns a FormResult:
    values   what the person typed, to show again in the form if something is wrong
    cleaned  what is safe to save (filled in only when there are no errors)
    errors   one short message for each field that is wrong

Medicine words are saved exactly as typed. The only change is that spaces at the very
start and very end are removed. Nothing is interpreted, translated or corrected.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.models import LANGUAGES

LANGUAGE_LABELS = {"hi": "Hindi", "mr": "Marathi"}
assert tuple(LANGUAGE_LABELS) == LANGUAGES, "language labels must match the database rule"

# Monday = 0 ... Sunday = 6, the same numbering as the repeat_days column
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_VALUES = {str(number) for number in range(7)}

# These limits match the size of the database columns
NAME_MAX = 100
ADDRESS_AS_MAX = 50
INSTRUCTION_MAX = 1000

# fullmatch (not match) so that anything after the time, such as "08:30pm" or "08:30 9", is refused.
# (Spaces and new lines at the very start or end were already removed by _clean.)
# [0-9] (not \d) so that digits from other scripts are refused.
_TIME = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
_PHONE = re.compile(r"\+?[0-9]{10,15}")
_DIGITS = re.compile(r"[0-9]+")


@dataclass
class FormResult:
    values: dict = field(default_factory=dict)
    cleaned: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _clean(data: Mapping, name: str) -> str:
    """The text of one field without spaces at either end ("" if it is missing)."""
    value = data.get(name, "")
    return value.strip() if isinstance(value, str) else ""


def _checked(data: Mapping, name: str) -> bool:
    """Was a checkbox ticked? A browser sends "on" for a ticked box and nothing for an empty one."""
    return _clean(data, name).lower() in ("on", "true", "1", "yes")


def _required_text(data: Mapping, name: str, label: str, max_length: int, errors: dict) -> str:
    value = _clean(data, name)
    if not value:
        errors[name] = f"{label} is required."
    elif len(value) > max_length:
        errors[name] = f"{label} must be {max_length} characters or fewer."
    return value


def validate_elder_form(data: Mapping) -> FormResult:
    """Check the "add elder" form. Consent must be ticked: no consent, no profile."""
    errors: dict = {}
    name = _required_text(data, "name", "Name", NAME_MAX, errors)
    address_as = _required_text(data, "address_as", "How to address them", ADDRESS_AS_MAX, errors)
    caregiver_name = _required_text(data, "caregiver_name", "Caregiver name", NAME_MAX, errors)

    phone_typed = _clean(data, "phone")
    phone = re.sub(r"[ -]", "", phone_typed)  # "+91 00000-00000" is saved as "+910000000000"
    if not phone_typed:
        errors["phone"] = "Phone number is required."
    elif not _PHONE.fullmatch(phone):
        errors["phone"] = "Enter 10 to 15 digits, optionally starting with +. Spaces and hyphens are allowed."

    language = _clean(data, "language")
    if language not in LANGUAGES:
        errors["language"] = "Choose Hindi or Marathi."

    consent = _checked(data, "consent")
    if not consent:
        errors["consent"] = "Consent must be confirmed before a profile can be saved."

    values = {
        "name": name,
        "address_as": address_as,
        "phone": phone_typed,
        "language": language,
        "caregiver_name": caregiver_name,
        "consent": consent,
    }
    cleaned = {}
    if not errors:
        cleaned = {
            "name": name,
            "address_as": address_as,
            "phone": phone,
            "language": language,
            "caregiver_name": caregiver_name,
            "consent_given": True,
        }
    return FormResult(values=values, cleaned=cleaned, errors=errors)


def validate_medicine_form(data: Mapping) -> FormResult:
    """Check the "add medicine" form. The three texts are saved exactly as the caregiver typed them."""
    errors: dict = {}
    name = _required_text(data, "name", "Medicine name", NAME_MAX, errors)
    spoken_name = _required_text(data, "spoken_name", "Spoken name", NAME_MAX, errors)

    instruction = _clean(data, "instruction_text")
    if len(instruction) > INSTRUCTION_MAX:
        errors["instruction_text"] = f"The instruction must be {INSTRUCTION_MAX} characters or fewer."

    values = {"name": name, "spoken_name": spoken_name, "instruction_text": instruction}
    cleaned = {}
    if not errors:
        cleaned = {
            "name": name,
            "spoken_name": spoken_name,
            "instruction_text": instruction or None,  # optional: empty means "none"
        }
    return FormResult(values=values, cleaned=cleaned, errors=errors)


def validate_schedule_form(
    data: Mapping, repeat_days: Sequence[str], allowed_medicine_ids: set[int]
) -> FormResult:
    """Check the "add schedule" form.

    allowed_medicine_ids are the medicines of THIS elder: a medicine of another elder is refused.
    A schedule is "verified" only if the box was ticked AND a name was typed. If the box is not
    ticked, any name that was typed is thrown away, so an unverified schedule never carries
    verification details. (The time of verification is added by the server, never by the form.)
    """
    errors: dict = {}

    medicine_typed = _clean(data, "medicine_id")
    medicine_id = None
    if not medicine_typed:
        errors["medicine_id"] = "Choose a medicine."
    elif not _DIGITS.fullmatch(medicine_typed) or int(medicine_typed) not in allowed_medicine_ids:
        errors["medicine_id"] = "Choose one of this elder's medicines."
    else:
        medicine_id = int(medicine_typed)

    time_of_day = _clean(data, "time_of_day")
    if not time_of_day:
        errors["time_of_day"] = "Time is required."
    elif not _TIME.fullmatch(time_of_day):
        errors["time_of_day"] = "Enter the time as HH:MM between 00:00 and 23:59, for example 08:30."

    chosen_days = [str(day).strip() for day in repeat_days]
    day_numbers: list[int] = []
    if not chosen_days:
        errors["repeat_days"] = "Choose at least one day."
    elif any(day not in DAY_VALUES for day in chosen_days):
        errors["repeat_days"] = "Choose days from Monday to Sunday only."
    else:
        day_numbers = sorted({int(day) for day in chosen_days})

    verified = _checked(data, "verified")
    verified_by_typed = _clean(data, "verified_by")
    if verified:
        if not verified_by_typed:
            errors["verified_by"] = "Enter the name of the person who checked this schedule."
        elif len(verified_by_typed) > NAME_MAX:
            errors["verified_by"] = f"The name must be {NAME_MAX} characters or fewer."

    values = {
        "medicine_id": medicine_typed,
        "time_of_day": time_of_day,
        "repeat_days": chosen_days,
        "verified": verified,
        "verified_by": verified_by_typed,
    }
    cleaned = {}
    if not errors:
        cleaned = {
            "medicine_id": medicine_id,
            "time_of_day": time_of_day,
            "repeat_days": ",".join(str(number) for number in day_numbers),
            "verified": verified,
            "verified_by": verified_by_typed if verified else None,
        }
    return FormResult(values=values, cleaned=cleaned, errors=errors)


def describe_days(repeat_days: str) -> str:
    """Turn "0,2,4" into "Mon, Wed, Fri", and all seven days into "Every day"."""
    numbers = sorted({int(day) for day in repeat_days.split(",") if day.strip().isdigit()})
    numbers = [number for number in numbers if 0 <= number <= 6]
    if numbers == list(range(7)):
        return "Every day"
    return ", ".join(DAY_SHORT[number] for number in numbers)
