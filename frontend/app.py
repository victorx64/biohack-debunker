import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


PASSWORD = "biohacker2026"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
DEFAULT_USER_EMAIL = os.getenv("STREAMLIT_USER_EMAIL", "streamlit@local")


st.set_page_config(page_title="Biohack Debunker", layout="wide")


def _api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def _api_request(method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body = None
    headers = {
        "Content-Type": "application/json",
        "x-user-email": DEFAULT_USER_EMAIL,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = Request(_api_url(path), data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read().decode("utf-8")
            if not data:
                return {}
            return json.loads(data)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"API error: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"API connection error: {exc}") from exc


def _get_query_params() -> Dict[str, Any]:
    try:
        return st.experimental_get_query_params()
    except AttributeError:
        return dict(st.query_params)


def _set_query_params(**kwargs: str) -> None:
    try:
        st.experimental_set_query_params(**kwargs)
    except AttributeError:
        st.query_params.update(kwargs)


st.title("Biohack Debunker")
params = _get_query_params()
analysis_id = None
if "analysis_id" in params:
    values = params.get("analysis_id")
    if isinstance(values, list) and values:
        analysis_id = values[0]
    elif isinstance(values, str):
        analysis_id = values

if analysis_id:
    st.subheader("Analysis status")
    try:
        analysis = _api_request("GET", f"/api/v1/analysis/{analysis_id}")
    except RuntimeError as exc:
        st.error(str(exc))
    else:
        status = analysis.get("status")
        if status in {"pending", "processing"}:
            st.info("Processing is in progress. Please refresh this page later.")
            if st.button("Refresh status"):
                st.experimental_rerun()
        elif status == "failed":
            st.error("Analysis failed. Please try again.")
        else:
            video = analysis.get("video") or {}
            st.subheader(video.get("title") or "Video analysis")
            if video.get("thumbnail_url"):
                st.image(video.get("thumbnail_url"), width=320)
            if video.get("channel"):
                st.caption(f"Channel: {video.get('channel')}")
            if video.get("duration"):
                st.caption(f"Duration: {video.get('duration')} sec")

            summary = analysis.get("summary")
            if summary:
                st.markdown("### Summary")
                st.write(summary)

            rating = analysis.get("overall_rating")
            if rating:
                st.markdown("### Overall rating")
                st.write(rating)

            claims = analysis.get("claims") or []
            if claims:
                st.markdown("### Claims")
                for claim in claims:
                    title = claim.get("text") or "Claim"
                    with st.expander(title, expanded=False):
                        timestamp = claim.get("timestamp")
                        if timestamp:
                            st.caption(f"Timestamp: {timestamp}")
                        if claim.get("verdict"):
                            st.write(f"Verdict: {claim.get('verdict')}")
                        if claim.get("confidence") is not None:
                            st.write(f"Confidence: {claim.get('confidence')}")
                        if claim.get("evidence_level"):
                            st.write(f"Evidence level: {claim.get('evidence_level')}")
                        if claim.get("study_type"):
                            st.write(f"Study type: {claim.get('study_type')}")
                        if claim.get("explanation"):
                            st.write(claim.get("explanation"))
                        sources = claim.get("sources") or []
                        if sources:
                            st.markdown("#### Sources")
                            for source in sources:
                                title = source.get("title") or "Source"
                                url = source.get("url")
                                if url:
                                    st.markdown(f"- [{title}]({url})")
                                else:
                                    st.markdown(f"- {title}")
            else:
                st.info("No claims available yet.")

    st.markdown("---")
    if st.button("Start a new analysis"):
        _set_query_params()
        st.experimental_rerun()
else:
    st.subheader("Start a new analysis")
    with st.form("analysis_form"):
        password = st.text_input("Password", type="password")
        youtube_url = st.text_input("YouTube URL")
        submitted = st.form_submit_button("Run analysis")

    if submitted:
        if password != PASSWORD:
            st.error("Invalid password.")
        elif not youtube_url:
            st.error("Please provide a YouTube URL.")
        else:
            try:
                payload = {"youtube_url": youtube_url, "is_public": True}
                response = _api_request("POST", "/api/v1/analysis", payload)
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                analysis_id = response.get("analysis_id")
                poll_url = response.get("poll_url")
                st.success("Analysis started.")
                if analysis_id:
                    st.markdown(
                        f"Open the results page: [View analysis](?analysis_id={analysis_id})"
                    )
                if poll_url:
                    st.caption(f"API status endpoint: {API_BASE_URL}{poll_url}")
                if response.get("status") in {"pending", "processing"}:
                    st.info("Processing is in progress. You can share the results link.")
