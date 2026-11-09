"""Tests for the two web addresses that exist in Milestone 1.

These tests use a test database and do NOT run the server's startup code (the lifespan in
app/main.py). Starting the real server by hand is a separate, mandatory check: see README.md.
"""


def test_health_says_server_and_database_are_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_home_page_opens_and_shows_the_safety_notice(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Dawai Saathi" in response.text
    assert "fictional data only" in response.text
    assert "does not verify" in response.text


def test_home_page_shows_zero_elders_in_a_new_database(client):
    response = client.get("/")

    assert "Elder profiles saved: <strong>0</strong>" in response.text


def test_stylesheet_is_served(client):
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "safety-banner" in response.text
