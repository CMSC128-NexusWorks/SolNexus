"""The mock app skeleton: health route and the error envelope, exercised in-process (no network)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_settings import MockServerSettings

CI_SETTINGS = MockServerSettings(environment="ci", log_level="INFO")


def test_health_reports_ok_and_which_environment_this_mock_is():
    client = TestClient(build_mock_google_app(CI_SETTINGS))

    response = client.get("/_mock/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "ci"}


def test_unknown_path_answers_with_the_error_envelope():
    client = TestClient(build_mock_google_app(CI_SETTINGS))

    response = client.get("/_mock/nothing-here")

    assert response.status_code == 404
    assert response.json() == {"success": False, "error": "NOT_FOUND", "message": "Not Found", "status": 404}


def test_unexpected_error_returns_a_generic_500_without_internal_details():
    app = build_mock_google_app(CI_SETTINGS)

    def broken_route():
        raise RuntimeError("internal detail that must not leak")

    app.add_api_route("/_mock/broken", broken_route)
    # raise_server_exceptions=False: assert on what a real caller would receive, not on the raised error.
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/_mock/broken")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "INTERNAL_ERROR" and body["success"] is False
    assert "internal detail" not in response.text and "Traceback" not in response.text
