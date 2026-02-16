import json
import os
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
import pytest
from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase


DEFAULT_DATASET_SOURCE = Path(__file__).with_name("fixtures")
DEFAULT_REPORT_OUTPUT_DIR = Path(__file__).with_name("outputs")
ALLOWED_VERDICTS = {
    "supported",
    "likely_supported",
    "conflicting",
    "insufficient_evidence",
    "likely_refuted",
    "refuted",
    "not_assessable",
}


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _f1(precision: float, recall: float) -> float:
    if precision + recall <= 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


@dataclass
class MatchResult:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]]
    missing_expected: list[dict[str, Any]]
    extra_actual: list[dict[str, Any]]


@dataclass
class MetricsAccumulator:
    extraction_tp: int = 0
    extraction_fp: int = 0
    extraction_fn: int = 0
    veracity_total: int = 0
    veracity_correct: int = 0
    invalid_actual_verdicts: int = 0
    invalid_expected_verdicts: int = 0
    confusion: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            expected: {actual: 0 for actual in sorted(ALLOWED_VERDICTS)}
            for expected in sorted(ALLOWED_VERDICTS)
        }
    )
    case_summaries: list[dict[str, Any]] = field(default_factory=list)

    def add_extraction_counts(self, tp: int, fp: int, fn: int) -> None:
        self.extraction_tp += tp
        self.extraction_fp += fp
        self.extraction_fn += fn

    def add_veracity_observation(self, expected: str, actual: str, is_correct: bool) -> None:
        self.veracity_total += 1
        if is_correct:
            self.veracity_correct += 1
        if expected in self.confusion and actual in self.confusion[expected]:
            self.confusion[expected][actual] += 1

    def add_case_summary(self, summary: dict[str, Any]) -> None:
        self.case_summaries.append(summary)

    def _veracity_per_class(self) -> dict[str, dict[str, float]]:
        per_class: dict[str, dict[str, float]] = {}
        for label in sorted(ALLOWED_VERDICTS):
            tp = self.confusion[label][label]
            fp = sum(self.confusion[other][label] for other in ALLOWED_VERDICTS if other != label)
            fn = sum(self.confusion[label][other] for other in ALLOWED_VERDICTS if other != label)
            precision = _safe_divide(tp, tp + fp)
            recall = _safe_divide(tp, tp + fn)
            per_class[label] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(_f1(precision, recall), 4),
                "support": int(sum(self.confusion[label].values())),
            }
        return per_class

    def to_report(self) -> dict[str, Any]:
        precision = _safe_divide(self.extraction_tp, self.extraction_tp + self.extraction_fp)
        recall = _safe_divide(self.extraction_tp, self.extraction_tp + self.extraction_fn)
        extraction_metrics = {
            "tp": self.extraction_tp,
            "fp": self.extraction_fp,
            "fn": self.extraction_fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
        }

        veracity_accuracy = _safe_divide(self.veracity_correct, self.veracity_total)
        per_class = self._veracity_per_class()
        macro_f1 = _safe_divide(
            sum(metrics["f1"] for metrics in per_class.values()),
            len(per_class),
        )
        total_support = sum(metrics["support"] for metrics in per_class.values())
        weighted_f1 = _safe_divide(
            sum(metrics["f1"] * metrics["support"] for metrics in per_class.values()),
            total_support,
        )

        confusion_matrix = {
            expected: {actual: int(count) for actual, count in row.items()}
            for expected, row in self.confusion.items()
        }

        return {
            "claim_extraction": extraction_metrics,
            "veracity": {
                "total": self.veracity_total,
                "correct": self.veracity_correct,
                "accuracy": round(veracity_accuracy, 4),
                "macro_f1": round(macro_f1, 4),
                "weighted_f1": round(weighted_f1, 4),
                "per_class": per_class,
                "confusion_matrix": confusion_matrix,
                "critical_flips": {
                    "supported_to_refuted": int(confusion_matrix["supported"]["refuted"]),
                    "refuted_to_supported": int(confusion_matrix["refuted"]["supported"]),
                },
                "invalid_actual_verdicts": self.invalid_actual_verdicts,
                "invalid_expected_verdicts": self.invalid_expected_verdicts,
            },
            "cases": self.case_summaries,
        }


_METRICS_ACCUMULATOR = MetricsAccumulator()


def _load_dataset() -> list[dict[str, Any]]:
    dataset_source = Path(
        os.getenv("DEEPEVAL_DATASET_PATH", str(DEFAULT_DATASET_SOURCE))
    )
    if not dataset_source.exists():
        raise AssertionError(f"dataset not found: {dataset_source}")

    if dataset_source.is_dir():
        case_files = sorted(
            path for path in dataset_source.glob("case-*.json") if path.is_file()
        )
        if not case_files:
            raise AssertionError(
                f"no case files found in dataset directory: {dataset_source}"
            )
        data: list[dict[str, Any]] = []
        for case_file in case_files:
            case_data = json.loads(case_file.read_text(encoding="utf-8"))
            if not isinstance(case_data, dict):
                raise AssertionError(
                    f"dataset case file must be a JSON object: {case_file}"
                )
            data.append(case_data)
    else:
        file_data = json.loads(dataset_source.read_text(encoding="utf-8"))
        if isinstance(file_data, list):
            data = file_data
        elif isinstance(file_data, dict):
            data = [file_data]
        else:
            raise AssertionError(
                "dataset file must be a JSON object or array of objects"
            )

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
    return data


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _expected_verdict_values(expected: dict[str, Any]) -> set[str]:
    expected_any_of = expected.get("verdict_any_of")
    if expected_any_of:
        expected_values = [str(item).strip().lower() for item in expected_any_of]
    else:
        expected_values = [str(expected.get("verdict") or "").strip().lower()]

    expected_norms = {value for value in expected_values if value}
    if not expected_norms:
        raise AssertionError("expected verdict is missing")

    unknown_expected = expected_norms - ALLOWED_VERDICTS
    if unknown_expected:
        raise AssertionError(
            "expected verdict contains unsupported enum value(s)\n"
            f"expected: {sorted(expected_norms)}\n"
            f"unknown: {sorted(unknown_expected)}\n"
            f"allowed: {sorted(ALLOWED_VERDICTS)}"
        )
    return expected_norms


def _expected_primary_verdict(expected: dict[str, Any]) -> str:
    expected_any_of = expected.get("verdict_any_of")
    if expected_any_of:
        primary = str(expected_any_of[0]).strip().lower()
    else:
        primary = str(expected.get("verdict") or "").strip().lower()
    if not primary:
        raise AssertionError("expected verdict is missing")
    if primary not in ALLOWED_VERDICTS:
        raise AssertionError(
            "expected verdict primary label is not a supported enum value\n"
            f"expected primary: {primary!r}\n"
            f"allowed: {sorted(ALLOWED_VERDICTS)}"
        )
    return primary


def _match_expected_claims(
    expected_claims: list[dict[str, Any]],
    actual_claims: list[dict[str, Any]],
    threshold: float,
) -> MatchResult:
    remaining_actual = actual_claims.copy()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    missing_expected: list[dict[str, Any]] = []

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
            missing_expected.append(expected)
            continue
        actual = remaining_actual.pop(best_index)
        pairs.append((expected, actual))

    return MatchResult(
        pairs=pairs,
        missing_expected=missing_expected,
        extra_actual=remaining_actual,
    )


def _verdict_matches(expected: dict[str, Any], actual_verdict: str) -> bool:
    actual_norm = str(actual_verdict).strip().lower()
    if actual_norm not in ALLOWED_VERDICTS:
        raise AssertionError(
            "actual verdict is not a supported enum value\n"
            f"actual: {actual_verdict!r}\n"
            f"allowed: {sorted(ALLOWED_VERDICTS)}"
        )

    expected_norms = _expected_verdict_values(expected)
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
    faithfulness_metric = FaithfulnessMetric(
        threshold=float(os.getenv("DEEPEVAL_FAITHFULNESS_THRESHOLD", "0.5")),
        model=model_name,
    )
    return [faithfulness_metric]


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


def _report_path() -> Path:
    explicit = os.getenv("DEEPEVAL_METRICS_REPORT_PATH", "").strip()
    if explicit:
        return Path(explicit)
    output_dir = os.getenv("DEEPEVAL_OUTPUT_DIR", "").strip()
    if output_dir:
        return Path(output_dir) / "metrics_summary.json"
    return DEFAULT_REPORT_OUTPUT_DIR / "metrics_summary.json"


@pytest.fixture(scope="session", autouse=True)
def _write_metrics_report_at_session_end() -> Any:
    yield
    report = _METRICS_ACCUMULATOR.to_report()
    report_path = _report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        "\n[deepeval] aggregate metrics | "
        f"extraction_f1={report['claim_extraction']['f1']:.4f} | "
        f"veracity_accuracy={report['veracity']['accuracy']:.4f} | "
        f"veracity_macro_f1={report['veracity']['macro_f1']:.4f} | "
        f"report={report_path}"
    )


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

    match_result = _match_expected_claims(expected_claims, actual_claims, threshold)
    pairs = match_result.pairs
    _METRICS_ACCUMULATOR.add_extraction_counts(
        tp=len(pairs),
        fp=len(match_result.extra_actual),
        fn=len(match_result.missing_expected),
    )

    failure_messages: list[str] = []
    if match_result.missing_expected:
        missing_descriptions = [
            str(item.get("claim") or "<missing claim text>") for item in match_result.missing_expected
        ]
        failure_messages.append(
            "missing expected claims: " + "; ".join(missing_descriptions)
        )

    max_claims = int(os.getenv("DEEPEVAL_MAX_CLAIMS_PER_CASE", "10"))

    metrics = _build_metrics(model_name)

    for index, (expected, actual) in enumerate(pairs[:max_claims], start=1):
        actual_verdict = str(actual.get("verdict") or "").strip()
        actual_norm = actual_verdict.lower()
        try:
            expected_primary = _expected_primary_verdict(expected)
            expected_allowed = _expected_verdict_values(expected)
        except AssertionError as exc:
            _METRICS_ACCUMULATOR.invalid_expected_verdicts += 1
            failure_messages.append(
                f"invalid expected verdict for claim index {index}: {exc}"
            )
            continue

        if actual_norm not in ALLOWED_VERDICTS:
            _METRICS_ACCUMULATOR.invalid_actual_verdicts += 1
            failure_messages.append(
                "actual verdict is not a supported enum value\n"
                f"claim: {actual.get('claim')}\n"
                f"actual: {actual_verdict!r}\n"
                f"allowed: {sorted(ALLOWED_VERDICTS)}"
            )
            continue

        is_verdict_correct = actual_norm in expected_allowed
        _METRICS_ACCUMULATOR.add_veracity_observation(
            expected=expected_primary,
            actual=actual_norm,
            is_correct=is_verdict_correct,
        )

        if not is_verdict_correct:
            failure_messages.append(
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
        try:
            assert_test(test_case, metrics)
        except AssertionError as exc:
            failure_messages.append(f"deepeval assertion failed for claim index {index}: {exc}")

    _METRICS_ACCUMULATOR.add_case_summary(
        {
            "case_id": str(case.get("id") or "case"),
            "expected_claims": len(expected_claims),
            "actual_claims": len(actual_claims),
            "matched_claims": len(pairs),
            "missing_claims": len(match_result.missing_expected),
            "extra_claims": len(match_result.extra_actual),
            "evaluated_veracity_claims": min(len(pairs), max_claims),
            "status": "failed" if failure_messages else "passed",
            "failure_count": len(failure_messages),
        }
    )

    if failure_messages:
        formatted = "\n---\n".join(failure_messages)
        raise AssertionError(f"case {case.get('id')}:\n{formatted}")
