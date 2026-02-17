import os

import httpx


def test_transcription_response() -> None:
    base_url = os.getenv("TRANSCRIPTION_BASE_URL", "http://localhost:8001").rstrip("/")
    youtube_url = os.getenv("TRANSCRIPTION_TEST_URL", "mock://video")

    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{base_url}/health")
        health.raise_for_status()
        response = client.post(
            f"{base_url}/transcription",
            json={"youtube_url": youtube_url},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"]
    assert payload["segments"]
    assert payload["video"]["youtube_id"]
