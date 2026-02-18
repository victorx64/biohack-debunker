import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytest


DEFAULT_REPORT_OUTPUT_DIR = Path(__file__).with_name("outputs")
CASE_METRICS_DIRNAME = ".case_metrics"
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


def _report_path() -> Path:
    explicit = os.getenv("DEEPEVAL_METRICS_REPORT_PATH", "").strip()
    if explicit:
        return Path(explicit)
    output_dir = os.getenv("DEEPEVAL_OUTPUT_DIR", "").strip()
    if output_dir:
        return Path(output_dir) / "metrics_summary.json"
    return DEFAULT_REPORT_OUTPUT_DIR / "metrics_summary.json"


def _run_id() -> str:
    explicit = os.getenv("DEEPEVAL_RUN_ID", "").strip()
    if explicit:
        return explicit
    xdist_run_id = os.getenv("PYTEST_XDIST_TESTRUNUID", "").strip()
    if xdist_run_id:
        return xdist_run_id
    fallback = f"local-{int(time.time())}"
    os.environ.setdefault("DEEPEVAL_RUN_ID", fallback)
    return os.getenv("DEEPEVAL_RUN_ID", fallback)


def _case_metrics_dir() -> Path:
    return _report_path().parent / CASE_METRICS_DIRNAME / _run_id()


def _is_xdist_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def _collect_case_metrics_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    metrics_dir = _case_metrics_dir()
    if not metrics_dir.exists():
        return records
    for case_file in sorted(metrics_dir.glob("*.json")):
        try:
            records.append(json.loads(case_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records


def _build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    extraction_tp = 0
    extraction_fp = 0
    extraction_fn = 0
    veracity_total = 0
    veracity_correct = 0
    invalid_actual_verdicts = 0
    invalid_expected_verdicts = 0
    case_summaries: list[dict[str, Any]] = []
    confusion = {
        expected: {actual: 0 for actual in sorted(ALLOWED_VERDICTS)}
        for expected in sorted(ALLOWED_VERDICTS)
    }

    for record in records:
        extraction = record.get("extraction") or {}
        extraction_tp += int(extraction.get("tp", 0))
        extraction_fp += int(extraction.get("fp", 0))
        extraction_fn += int(extraction.get("fn", 0))

        for observation in record.get("veracity_observations") or []:
            expected = str(observation.get("expected") or "").strip().lower()
            actual = str(observation.get("actual") or "").strip().lower()
            if expected not in ALLOWED_VERDICTS or actual not in ALLOWED_VERDICTS:
                continue
            veracity_total += 1
            if bool(observation.get("is_correct", False)):
                veracity_correct += 1
            confusion[expected][actual] += 1

        invalid_actual_verdicts += int(record.get("invalid_actual_verdicts", 0))
        invalid_expected_verdicts += int(record.get("invalid_expected_verdicts", 0))

        summary = record.get("summary")
        if isinstance(summary, dict):
            case_summaries.append(summary)

    extraction_precision = _safe_divide(extraction_tp, extraction_tp + extraction_fp)
    extraction_recall = _safe_divide(extraction_tp, extraction_tp + extraction_fn)

    per_class: dict[str, dict[str, float]] = {}
    for label in sorted(ALLOWED_VERDICTS):
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in ALLOWED_VERDICTS if other != label)
        fn = sum(confusion[label][other] for other in ALLOWED_VERDICTS if other != label)
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
            "support": int(sum(confusion[label].values())),
        }

    macro_f1 = _safe_divide(
        sum(metrics["f1"] for metrics in per_class.values()),
        len(per_class),
    )
    total_support = sum(metrics["support"] for metrics in per_class.values())
    weighted_f1 = _safe_divide(
        sum(metrics["f1"] * metrics["support"] for metrics in per_class.values()),
        total_support,
    )

    return {
        "claim_extraction": {
            "tp": extraction_tp,
            "fp": extraction_fp,
            "fn": extraction_fn,
            "precision": round(extraction_precision, 4),
            "recall": round(extraction_recall, 4),
            "f1": round(_f1(extraction_precision, extraction_recall), 4),
        },
        "veracity": {
            "total": veracity_total,
            "correct": veracity_correct,
            "accuracy": round(_safe_divide(veracity_correct, veracity_total), 4),
            "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(weighted_f1, 4),
            "per_class": per_class,
            "confusion_matrix": confusion,
            "critical_flips": {
                "supported_to_refuted": int(confusion["supported"]["refuted"]),
                "refuted_to_supported": int(confusion["refuted"]["supported"]),
            },
            "invalid_actual_verdicts": invalid_actual_verdicts,
            "invalid_expected_verdicts": invalid_expected_verdicts,
        },
        "cases": case_summaries,
    }


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    if _is_xdist_worker(session.config):
        return
    target_dir = _case_metrics_dir()
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    if _is_xdist_worker(session.config):
        return
    records = _collect_case_metrics_records()
    report = _build_report(records)
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
