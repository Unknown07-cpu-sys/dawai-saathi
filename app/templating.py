"""The Jinja2 template engine, created once so every route can share it.

A template is an HTML file with small gaps like {{ app_name }} that Python fills in.
"""

from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
