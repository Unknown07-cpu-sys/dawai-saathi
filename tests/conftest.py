"""Shared test setup (pytest loads this file automatically).

Every test gets its OWN brand-new database that lives only in memory. So tests never
touch data/dawai.db, and one test can never disturb another.

IMPORTANT LIMIT OF THIS TEST SUITE: it does NOT run the app's startup code (the FastAPI
"lifespan" in app/main.py, which creates the tables of the real data/dawai.db). The tests
build their own tables with init_db(engine) instead. So a green pytest run does not prove
that the real server starts. That is why the manual startup check in README.md
("Mandatory completion check") must also pass before Milestone 1 counts as finished.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import get_db, init_db, make_engine
from app.main import app


@pytest.fixture
def engine():
    """A fresh, empty, in-memory database with all seven tables created."""
    test_engine = make_engine("sqlite://")
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine):
    """A database session for tests that talk to the database directly."""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(engine):
    """A pretend browser. It talks to the real app, but the app uses the test database."""
    test_session_factory = sessionmaker(bind=engine)

    def use_test_database():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    # "Whenever a route asks for get_db, give it the test database instead."
    app.dependency_overrides[get_db] = use_test_database
    # No "with" here on purpose: "with TestClient(app)" would run the lifespan startup code
    # and create the real data/dawai.db. Without it the lifespan is NOT run (see the top of this file).
    yield TestClient(app)
    app.dependency_overrides.clear()
