import os

import httpx
import pytest


@pytest.mark.anyio
async def test_transcription_real_response() -> None:
    youtube_url = os.getenv("TRANSCRIPTION_REAL_URL")
    if not youtube_url:
        pytest.skip("TRANSCRIPTION_REAL_URL is not set")

    from transcription_service import main as main_module

    async with main_module.app.router.lifespan_context(main_module.app):
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            timeout=60.0,
        ) as client:
            response = await client.post(
                "/transcription",
                json={"youtube_url": youtube_url},
            )

        if response.status_code != 200:
            if "429" in response.text or "Too Many Requests" in response.text:
                pytest.skip("YouTube rate limited the caption request")
        assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"]
    assert payload["segments"]
    assert payload["video"]["youtube_id"]
