import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
import pytest
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.test_case import LLMTestCase

try:
    from deepeval.test_case import LLMTestCaseParams
except ImportError:  # Backward compatibility for older DeepEval versions.
    class LLMTestCaseParams:  # type: ignore[no-redef]
        INPUT = "input"
        ACTUAL_OUTPUT = "actual_output"
        EXPECTED_OUTPUT = "expected_output"
        RETRIEVAL_CONTEXT = "retrieval_context"


DEFAULT_DATASET_PATH = Path(__file__).with_name("fixtures").joinpath("analysis_dataset.json")


def _load_dataset() -> list[dict[str, Any]]:
    dataset_path = Path(os.getenv("DEEPEVAL_DATASET_PATH", str(DEFAULT_DATASET_PATH)))
    if not dataset_path.exists():
        raise AssertionError(f"dataset not found: {dataset_path}")
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AssertionError("dataset must be a JSON array")
    if not data:
        raise AssertionError("dataset is empty")
    case_ids_raw = os.getenv("DEEPEVAL_CASE_IDS", "").strip()
    if case_ids_raw:
        wanted_ids = {item.strip() for item in case_ids_raw.split(",") if item.strip()}
        data = [item for item in data if str(item.get("id") or "") in wanted_ids]
        if not data:
            raise AssertionError(
                f"no dataset cases matched DEEPEVAL_CASE_IDS={case_ids_raw!r}"
            )
    max_cases_raw = os.getenv("DEEPEVAL_MAX_CASES", "").strip()
    if max_cases_raw:
        max_cases = int(max_cases_raw)
        if max_cases < 1:
            raise AssertionError("DEEPEVAL_MAX_CASES must be >= 1")
        data = data[:max_cases]
    return data


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _match_expected_claims(
    expected_claims: list[dict[str, Any]],
    actual_claims: list[dict[str, Any]],
    threshold: float,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    remaining_actual = actual_claims.copy()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for expected in expected_claims:
        expected_text = str(expected.get("claim") or "").strip()
        if not expected_text:
            raise AssertionError("expected claim text is missing")
        best_index = None
        best_score = -1.0
        for index, actual in enumerate(remaining_actual):
            actual_text = str(actual.get("claim") or "").strip()
            score = _similarity(expected_text, actual_text)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None or best_score < threshold:
            raise AssertionError(
                "no close match for expected claim\n"
                f"expected: {expected_text}\n"
                f"best_score: {best_score:.2f} (threshold {threshold:.2f})"
            )
        actual = remaining_actual.pop(best_index)
        pairs.append((expected, actual))

    return pairs


def _verdict_matches(expected: dict[str, Any], actual_verdict: str) -> bool:
    actual_norm = _normalize_text(actual_verdict)
    expected_any_of = expected.get("verdict_any_of")
    if expected_any_of:
        expected_values = [str(item) for item in expected_any_of]
    else:
        expected_values = [str(expected.get("verdict") or "")]
    expected_norms = {_normalize_text(value) for value in expected_values if value.strip()}
    if not expected_norms:
        raise AssertionError("expected verdict is missing")
    return actual_norm in expected_norms


def _expected_verdict_output(expected: dict[str, Any]) -> str:
    expected_any_of = expected.get("verdict_any_of")
    if expected_any_of:
        values = [str(item) for item in expected_any_of if str(item).strip()]
        return " / ".join(values)
    return str(expected.get("verdict") or "").strip()


def _format_retrieval_context(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return ["No evidence sources provided."]
    context_items: list[str] = []
    for source in sources:
        title = str(source.get("title") or "").strip()
        snippet = str(source.get("snippet") or "").strip()
        if title and snippet:
            context_items.append(f"{title} - {snippet}")
        elif title:
            context_items.append(title)
        elif snippet:
            context_items.append(snippet)
    return context_items or ["No evidence sources provided."]


def _build_metrics(model_name: str) -> list[Any]:
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        # Ensure DeepEval/OpenAI client uses the same base URL from .env.
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ.setdefault("OPENAI_API_BASE", base_url)
    verdict_metric = GEval(
        name="Verdict match",
        criteria="Determine whether the actual verdict matches the expected verdict.",
        evaluation_steps=[
            "Read the expected verdict.",
            "Read the actual verdict.",
            "Return a high score when they match in meaning.",
        ],
        evaluation_params=[
            LLMTestCaseParams.EXPECTED_OUTPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=float(os.getenv("DEEPEVAL_VERDICT_THRESHOLD", "0.8")),
        model=model_name,
    )

    faithfulness_metric = FaithfulnessMetric(
        threshold=float(os.getenv("DEEPEVAL_FAITHFULNESS_THRESHOLD", "0.5")),
        model=model_name,
    )
    return [verdict_metric, faithfulness_metric]


def _wait_for_service(base_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    health_url = f"{base_url.rstrip('/')}/health"
    while time.time() < deadline:
        try:
            response = httpx.get(health_url, timeout=10)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("analysis service not ready")


def _post_analysis(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    _wait_for_service(base_url)
    response = httpx.post(f"{base_url.rstrip('/')}/analyze", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def _save_response(case_id: str | None, response: dict[str, Any]) -> None:
    output_dir = os.getenv("DEEPEVAL_OUTPUT_DIR", "").strip()
    if not output_dir:
        return
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_id = (case_id or "case").replace("/", "-")
    file_path = target_dir / f"{safe_id}.json"
    file_path.write_text(json.dumps(response, ensure_ascii=True, indent=2), encoding="utf-8")


@pytest.mark.parametrize("case", _load_dataset())
def test_deepeval_analysis(case: dict[str, Any]) -> None:
    base_url = os.getenv("ANALYSIS_BASE_URL", "http://analysis-service:8002")
    threshold = float(os.getenv("DEEPEVAL_CLAIM_MATCH_THRESHOLD", "0.6"))
    model_name = os.getenv("DEEPEVAL_MODEL", "gpt-4o-mini")

    segments = case.get("segments") or []
    if not segments:
        raise AssertionError("segments are required")

    analysis_params = case.get("analysis_params") or {}
    research_max_results_override_raw = os.getenv(
        "DEEPEVAL_RESEARCH_MAX_RESULTS_OVERRIDE", ""
    ).strip()
    research_max_results = analysis_params.get("research_max_results", 5)
    if research_max_results_override_raw:
        research_max_results = int(research_max_results_override_raw)

    payload = {
        "segments": segments,
        "claims_per_chunk": analysis_params.get("claims_per_chunk", 6),
        "chunk_size_chars": analysis_params.get("chunk_size_chars", 5000),
        "research_max_results": research_max_results,
        "research_sources": analysis_params.get("research_sources", ["pubmed"]),
    }

    response = _post_analysis(base_url, payload)
    _save_response(str(case.get("id") or "case"), response)
    actual_claims = response.get("claims") or []
    expected_claims = case.get("expected_claims") or []
    if not expected_claims:
        raise AssertionError("expected_claims are required")

    pairs = _match_expected_claims(expected_claims, actual_claims, threshold)
    max_claims = int(os.getenv("DEEPEVAL_MAX_CLAIMS_PER_CASE", "10"))

    metrics = _build_metrics(model_name)

    for index, (expected, actual) in enumerate(pairs[:max_claims], start=1):
        actual_verdict = str(actual.get("verdict") or "").strip()
        if not _verdict_matches(expected, actual_verdict):
            raise AssertionError(
                "verdict mismatch\n"
                f"expected: {expected.get('verdict') or expected.get('verdict_any_of')}\n"
                f"actual: {actual_verdict}"
            )

        actual_explanation = str(actual.get("explanation") or "").strip()
        actual_claim = str(actual.get("claim") or "").strip()
        sources = actual.get("sources") or []
        test_case = LLMTestCase(
            input=actual_claim,
            actual_output=f"Verdict: {actual_verdict}\nExplanation: {actual_explanation}",
            expected_output=_expected_verdict_output(expected),
            retrieval_context=_format_retrieval_context(sources),
            metadata={
                "case_id": case.get("id"),
                "claim_index": index,
            },
        )
        assert_test(test_case, metrics)
