"""Services: the logic of the app, kept apart from web pages so it can be tested without a browser.

Planned modules, added one milestone at a time:
    reminders.py       M3  create reminder occurrences, record call attempts and retries
    intents.py         M4  the Hindi/Marathi rule engine: words in, report type out
    reports.py         M4  save an elder report and update the reminder's status
    speech.py          M5  adapters for Sarvam speech-to-text and text-to-speech
    history.py         M6  read-only answers to "did I report my BP medicine?"
    notifications.py   M7  caregiver alerts and the daily summary
"""
