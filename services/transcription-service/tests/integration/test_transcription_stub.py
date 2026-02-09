import os

import httpx
import pytest


@pytest.mark.anyio
async def test_transcription_stub_response() -> None:
    os.environ["TRANSCRIPTION_USE_STUBS"] = "true"
    from transcription_service import main as main_module

    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/transcription",
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["video"]["youtube_id"] == "dQw4w9WgXcQ"
    assert payload["transcript"]
    assert payload["warnings"]
