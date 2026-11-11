"""The Jinja2 template engine, created once so every route can share it.

A template is an HTML file with small gaps like {{ app_name }} that Python fills in.
Jinja2 turns characters such as < and & into harmless text automatically, so something a
caregiver types can never become part of the page's code.
"""

from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings
from app.services.forms import describe_days
from app.timeutil import format_ist

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Available in every template
templates.env.globals["app_name"] = settings.app_name
# Small helpers used inside templates as {{ value | ist }} and {{ value | days }}
templates.env.filters["ist"] = format_ist
templates.env.filters["days"] = describe_days
