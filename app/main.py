"""The front door of the app. Start it from the project folder with:

    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.db import init_db
from app.routes import health, pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts: make sure the database tables exist."""
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Files in app/static (CSS now, the phone simulator's JavaScript later) are served under /static
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

app.include_router(health.router)
app.include_router(pages.router)
