from __future__ import annotations

import os
import time

import httpx


BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")


def _wait_for_completion(client: httpx.Client, analysis_id: str, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"{BASE_URL}/api/v1/analysis/{analysis_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = payload.get("status")
        if status == "completed":
            return payload
        if status == "failed":
            raise AssertionError("analysis failed")
        time.sleep(1.0)
    raise AssertionError(f"analysis did not complete in {timeout_s}s; last={last_payload}")


def test_gateway_health_and_flow() -> None:
    with httpx.Client(timeout=30) as client:
        health = client.get(f"{BASE_URL}/health")
        health.raise_for_status()
        payload = health.json()
        assert payload.get("status") in {"healthy", "degraded"}

        create = client.post(
            f"{BASE_URL}/api/v1/analysis",
            json={"youtube_url": "mock://video"},
            headers={"x-user-email": "integration@test.local"},
        )
        assert create.status_code == 202
        data = create.json()
        analysis_id = data.get("analysis_id")
        assert analysis_id

        result = _wait_for_completion(client, analysis_id)
        assert result.get("status") == "completed"
        assert result.get("summary")
        assert result.get("overall_rating")
        claims = result.get("claims") or []
        assert claims
        for claim in claims:
            assert claim.get("text")
            assert claim.get("verdict")
