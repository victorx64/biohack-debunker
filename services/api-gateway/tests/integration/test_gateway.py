from __future__ import annotations

import os
import time
from uuid import uuid4

import httpx


BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")
USER_EMAIL = os.getenv("GATEWAY_TEST_USER_EMAIL", "integration@test.local")
POLL_TIMEOUT_S = int(os.getenv("GATEWAY_POLL_TIMEOUT_S", "180"))


def _wait_for_terminal_state(
    client: httpx.Client,
    analysis_id: str,
    timeout_s: int = POLL_TIMEOUT_S,
) -> dict:
    deadline = time.time() + timeout_s
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"{BASE_URL}/api/v1/analysis/{analysis_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = payload.get("status")
        if status in {"completed", "failed"}:
            return payload
        time.sleep(1.0)
    raise AssertionError(
        f"analysis did not reach terminal state in {timeout_s}s; last={last_payload}"
    )


def _create_analysis(client: httpx.Client, youtube_url: str, force: bool = False) -> dict:
    payload = {"youtube_url": youtube_url}
    if force:
        payload["force"] = True
    response = client.post(
        f"{BASE_URL}/api/v1/analysis",
        json=payload,
        headers={"x-user-email": USER_EMAIL},
    )
    assert response.status_code == 202
    data = response.json()
    assert data.get("analysis_id")
    assert data.get("status") in {"pending", "processing", "completed"}
    assert data.get("poll_url")
    return data


def test_gateway_health() -> None:
    with httpx.Client(timeout=30) as client:
        health = client.get(f"{BASE_URL}/health")
        health.raise_for_status()
        payload = health.json()
        assert payload.get("status") in {"healthy", "degraded"}
        services = payload.get("services") or {}
        assert "database" in services
        assert "redis" in services
        assert "transcription_service" in services
        assert "analysis_service" in services


def test_create_analysis_idempotency_and_force() -> None:
    with httpx.Client(timeout=30) as client:
        youtube_url = f"mock://video/{uuid4()}"
        first = _create_analysis(client, youtube_url)
        analysis_id = first.get("analysis_id")
        assert analysis_id

        same = _create_analysis(client, youtube_url)
        assert same.get("analysis_id") == analysis_id

        forced = _create_analysis(client, youtube_url, force=True)
        assert forced.get("analysis_id") != analysis_id


def test_get_analysis_not_found() -> None:
    with httpx.Client(timeout=30) as client:
        missing = client.get(f"{BASE_URL}/api/v1/analysis/00000000-0000-0000-0000-000000000000")
        assert missing.status_code == 404
        payload = missing.json()
        assert payload.get("detail") == "Analysis not found"


def test_analysis_reaches_terminal_state() -> None:
    with httpx.Client(timeout=30) as client:
        youtube_url = f"mock://video/{uuid4()}"
        created = _create_analysis(client, youtube_url, force=True)
        analysis_id = created.get("analysis_id")
        assert analysis_id

        result = _wait_for_terminal_state(client, analysis_id)
        status = result.get("status")
        assert status in {"completed", "failed"}

        if status == "completed":
            assert result.get("summary")
            assert result.get("overall_rating")
            claims = result.get("claims") or []
            assert claims
            for claim in claims:
                assert claim.get("text")
                assert claim.get("verdict")

