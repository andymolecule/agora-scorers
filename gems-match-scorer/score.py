"""
Agora Exact-Match Scorer

Supports deterministic exact-match scoring for:
  - csv_table submissions compared against a reference CSV
  - json_file submissions compared against a reference JSON document
  - json_file submissions validated against a hidden structured-record rubric
  - opaque_file submissions compared byte-for-byte against a reference artifact

Input:
  /input/agora-runtime.json
  /input/<evaluation bundle>
  /input/<submission artifact>

Output:
  /output/score.json
"""

import csv
import json
import math
import os
from pathlib import Path

INPUT_DIR = Path("/input")
OUTPUT_DIR = Path("/output")
RUNTIME_CONFIG_PATH = INPUT_DIR / "agora-runtime.json"
OUTPUT_PATH = OUTPUT_DIR / "score.json"

DEFAULT_EVALUATION_BUNDLE_NAME = "ground_truth.csv"
DEFAULT_SUBMISSION_FILE_NAME = "submission.csv"


def deterministic_json_write(payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    OUTPUT_PATH.write_text(serialized, encoding="utf-8")


def fail_runtime(message: str) -> None:
    deterministic_json_write({"ok": False, "score": 0.0, "error": message, "details": {}})
    raise SystemExit(1)


def reject_submission(message: str, details: dict | None = None) -> None:
    deterministic_json_write(
        {
            "ok": False,
            "score": 0.0,
            "error": message,
            "details": details or {},
        }
    )
    raise SystemExit(0)


def require_csv_submission_contract(contract: dict) -> None:
    columns = contract.get("columns")
    if not isinstance(columns, dict):
        fail_runtime("CSV submission contract is missing columns.")
    required = columns.get("required")
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(column, str) and column for column in required)
    ):
        fail_runtime("CSV submission contract must declare required columns.")


def resolve_json_submission_mode(metric: str) -> str:
    if metric == "validation_score":
        return "json_record"
    return "json_file"


def resolve_opaque_submission_mode(contract: dict, metric: str) -> str:
    file_contract = contract.get("file")
    if not isinstance(file_contract, dict):
        fail_runtime("Opaque submission contract is missing file metadata.")
    extension = file_contract.get("extension")
    mime = file_contract.get("mime")
    if extension == ".json" or mime == "application/json":
        return resolve_json_submission_mode(metric)
    return "opaque_file"


def load_runtime_config() -> dict:
    if not RUNTIME_CONFIG_PATH.exists():
        return {
            "comparison_kind": "csv_table",
            "evaluation_path": INPUT_DIR / DEFAULT_EVALUATION_BUNDLE_NAME,
            "submission_path": INPUT_DIR / DEFAULT_SUBMISSION_FILE_NAME,
        }

    try:
        runtime_config = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail_runtime(
            f"Invalid runtime config JSON at /input/agora-runtime.json: {error.msg}"
        )

    if runtime_config.get("version") != "v1":
        fail_runtime("Unsupported runtime config version. Expected version=v1.")

    mount = runtime_config.get("mount")
    if not isinstance(mount, dict):
        fail_runtime("Runtime config mount must be an object.")

    evaluation_bundle_name = mount.get("evaluation_bundle_name")
    submission_file_name = mount.get("submission_file_name")
    if not isinstance(evaluation_bundle_name, str) or not evaluation_bundle_name:
        fail_runtime("Runtime config evaluation_bundle_name must be a non-empty string.")
    if not isinstance(submission_file_name, str) or not submission_file_name:
        fail_runtime("Runtime config submission_file_name must be a non-empty string.")

    metric = runtime_config.get("metric", "custom")
    submission_contract = runtime_config.get("submission_contract")
    if not isinstance(submission_contract, dict):
        fail_runtime("Runtime config submission_contract must be an object.")

    comparison_kind = submission_contract.get("kind")
    if comparison_kind == "csv_table":
        require_csv_submission_contract(submission_contract)
    elif comparison_kind == "json_file":
        comparison_kind = resolve_json_submission_mode(metric)
    elif comparison_kind == "opaque_file":
        comparison_kind = resolve_opaque_submission_mode(submission_contract, metric)
    else:
        fail_runtime(
            "official exact-match and structured-record scorers currently support csv_table, json_file, and opaque_file submissions."
        )

    return {
        "comparison_kind": comparison_kind,
        "evaluation_path": INPUT_DIR / evaluation_bundle_name,
        "submission_path": INPUT_DIR / submission_file_name,
    }


def read_csv_rows(path: Path, label: str, runtime_error: bool) -> list[dict[str, str]]:
    if not path.exists():
        message = f"Missing required file: {path}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception as error:
        message = f"{label} is not valid CSV data: {error}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)
    raise AssertionError("unreachable")


def is_empty_csv(rows: list[dict[str, str]]) -> bool:
    return len(rows) == 0


def is_numeric_value(value: str | None) -> bool:
    if value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def compare_csv_exact_match(evaluation_path: Path, submission_path: Path) -> None:
    tolerance = float(os.getenv("AGORA_TOLERANCE", "0.001"))
    truth = read_csv_rows(evaluation_path, "Evaluation bundle", True)
    submission = read_csv_rows(submission_path, "Submission", False)

    if is_empty_csv(truth):
        deterministic_json_write(
            {
                "ok": True,
                "details": {
                    "comparison_kind": "csv_table",
                    "comparable_rows": 0,
                    "mismatched_row_penalty": 0,
                    "selected_metric": "exact_match",
                    "selected_metric_value": 1.0,
                    "tolerance": tolerance,
                },
                "matched_rows": 0,
                "score": 1.0,
                "total_rows": 0,
            }
        )
        return

    truth_columns = list(truth[0].keys())
    submission_columns = list(submission[0].keys()) if submission else []
    missing_columns = [column for column in truth_columns if column not in submission_columns]
    if missing_columns:
        reject_submission(
            f"Submission missing required columns: {','.join(missing_columns)}",
            {"missing_columns": missing_columns},
        )

    total_rows = len(truth)
    comparable_rows = min(len(truth), len(submission))

    matched_rows = 0
    for row_index in range(comparable_rows):
        truth_row = truth[row_index]
        submission_row = submission[row_index]
        row_matches = True
        for column in truth_columns:
            truth_value = truth_row.get(column)
            submission_value = submission_row.get(column)
            if truth_value == "" and submission_value == "":
                continue
            if is_numeric_value(truth_value) and is_numeric_value(submission_value):
                if not math.isclose(
                    float(truth_value),
                    float(submission_value),
                    abs_tol=tolerance,
                    rel_tol=0.0,
                ):
                    row_matches = False
                    break
            else:
                if str(truth_value) != str(submission_value):
                    row_matches = False
                    break
        if row_matches:
            matched_rows += 1

    mismatched_row_penalty = abs(len(truth) - len(submission))
    denominator = total_rows if total_rows > 0 else max(len(submission), 1)
    score = max(matched_rows - mismatched_row_penalty, 0) / denominator

    deterministic_json_write(
        {
            "ok": True,
            "details": {
                "comparison_kind": "csv_table",
                "comparable_rows": comparable_rows,
                "mismatched_row_penalty": mismatched_row_penalty,
                "selected_metric": "exact_match",
                "selected_metric_value": float(round(score, 12)),
                "tolerance": tolerance,
            },
            "matched_rows": matched_rows,
            "score": float(round(score, 12)),
            "total_rows": int(total_rows),
        }
    )


def read_json_document(path: Path, label: str, runtime_error: bool):
    if not path.exists():
        message = f"Missing required file: {path}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        message = f"{label} is not valid JSON: {error.msg}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    raise AssertionError("unreachable")


def compare_json_exact_match(evaluation_path: Path, submission_path: Path) -> None:
    truth = read_json_document(evaluation_path, "Evaluation bundle", True)
    submission = read_json_document(submission_path, "Submission", False)
    matched = truth == submission
    score = 1.0 if matched else 0.0

    deterministic_json_write(
        {
            "ok": True,
            "details": {
                "comparison_kind": "json_file",
                "selected_metric": "exact_match",
                "selected_metric_value": score,
            },
            "matched_rows": 1 if matched else 0,
            "score": score,
            "total_rows": 1,
        }
    )


def normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]


def has_present_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def parse_allowed_string_values(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for field, options in value.items():
        if not isinstance(field, str):
            continue
        normalized_options = normalize_string_list(options)
        if normalized_options:
            normalized[field] = normalized_options
    return normalized


def parse_structured_record_rubric(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        fail_runtime("Structured record rubric must be a JSON object.")

    required_fields = normalize_string_list(
        document.get("required_fields") or document.get("required_sections")
    )
    non_empty_array_fields = normalize_string_list(
        document.get("non_empty_array_fields")
    )
    allowed_string_values = parse_allowed_string_values(
        document.get("allowed_string_values")
    )

    checks_total = (
        len(required_fields)
        + len(non_empty_array_fields)
        + len(allowed_string_values)
    )
    if checks_total == 0:
        fail_runtime(
            "Structured record rubric must declare at least one deterministic validation rule using required_fields, required_sections, non_empty_array_fields, or allowed_string_values."
        )

    return {
        "required_fields": required_fields,
        "non_empty_array_fields": non_empty_array_fields,
        "allowed_string_values": allowed_string_values,
    }


def compare_structured_record_validation(
    evaluation_path: Path, submission_path: Path
) -> None:
    rubric_document = read_json_document(evaluation_path, "Evaluation bundle", True)
    submission = read_json_document(submission_path, "Submission", False)
    if not isinstance(submission, dict):
        reject_submission(
            "Submission must be a JSON object.",
            {"comparison_kind": "json_record"},
        )

    rubric = parse_structured_record_rubric(rubric_document)
    required_fields = rubric["required_fields"]
    non_empty_array_fields = rubric["non_empty_array_fields"]
    allowed_string_values = rubric["allowed_string_values"]

    checks_passed = 0
    failed_checks: list[str] = []

    for field in required_fields:
        if has_present_value(submission.get(field)):
            checks_passed += 1
        else:
            failed_checks.append(f"missing_or_empty:{field}")

    for field in non_empty_array_fields:
        value = submission.get(field)
        if isinstance(value, list) and len(value) > 0:
            checks_passed += 1
        else:
            failed_checks.append(f"array_required:{field}")

    for field, allowed_values in allowed_string_values.items():
        value = submission.get(field)
        if isinstance(value, str) and value in allowed_values:
            checks_passed += 1
        else:
            failed_checks.append(f"allowed_value:{field}")

    checks_total = (
        len(required_fields)
        + len(non_empty_array_fields)
        + len(allowed_string_values)
    )
    score = checks_passed / checks_total

    deterministic_json_write(
        {
            "ok": True,
            "details": {
                "comparison_kind": "json_record",
                "selected_metric": "validation_score",
                "selected_metric_value": float(round(score, 12)),
                "checks_passed": checks_passed,
                "checks_total": checks_total,
                "failed_checks": failed_checks,
            },
            "matched_rows": checks_passed,
            "score": float(round(score, 12)),
            "total_rows": checks_total,
        }
    )


def read_binary_document(path: Path, label: str, runtime_error: bool) -> bytes:
    if not path.exists():
        message = f"Missing required file: {path}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    try:
        return path.read_bytes()
    except Exception as error:
        message = f"{label} could not be read as bytes: {error}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    raise AssertionError("unreachable")


def compare_opaque_exact_match(evaluation_path: Path, submission_path: Path) -> None:
    truth = read_binary_document(evaluation_path, "Evaluation bundle", True)
    submission = read_binary_document(submission_path, "Submission", False)
    matched = truth == submission
    score = 1.0 if matched else 0.0

    deterministic_json_write(
        {
            "ok": True,
            "details": {
                "comparison_kind": "opaque_file",
                "selected_metric": "exact_match",
                "selected_metric_value": score,
            },
            "matched_rows": 1 if matched else 0,
            "score": score,
            "total_rows": 1,
        }
    )


def main() -> None:
    runtime_config = load_runtime_config()
    evaluation_path = runtime_config["evaluation_path"]
    submission_path = runtime_config["submission_path"]

    if runtime_config["comparison_kind"] == "csv_table":
        compare_csv_exact_match(evaluation_path, submission_path)
        return

    if runtime_config["comparison_kind"] == "json_file":
        compare_json_exact_match(evaluation_path, submission_path)
        return

    if runtime_config["comparison_kind"] == "json_record":
        compare_structured_record_validation(evaluation_path, submission_path)
        return

    compare_opaque_exact_match(evaluation_path, submission_path)


if __name__ == "__main__":
    main()
