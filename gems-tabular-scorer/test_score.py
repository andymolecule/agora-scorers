import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "lifecycle" / "prediction"
MODULE_PATH = ROOT_DIR / "containers" / "gems-tabular-scorer" / "score.py"


def load_scorer_module():
    spec = importlib.util.spec_from_file_location("agora_regression_scorer", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load regression scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_config(id_column: str, value_column: str, metric: str = "r2") -> dict:
    return {
        "version": "v1",
        "template": "official_table_metric_v1",
        "metric": metric,
        "mount": {
            "evaluation_bundle_name": "ground_truth.csv",
            "submission_file_name": "submission.csv",
        },
        "submission_contract": {
            "version": "v1",
            "kind": "csv_table",
            "columns": {
                "required": [id_column, value_column],
                "id": id_column,
                "value": value_column,
                "allow_extra": True,
            },
        },
        "evaluation_contract": {
            "kind": "csv_table",
            "columns": {
                "required": ["id", "label"],
                "id": "id",
                "value": "label",
                "allow_extra": True,
            },
        },
        "policies": {
            "coverage_policy": "reject",
            "duplicate_id_policy": "reject",
            "invalid_value_policy": "reject",
        },
    }


def run_case(
    submission_text: str,
    id_column: str = "id",
    value_column: str = "prediction",
    metric: str = "r2",
    ground_truth_text: str | None = None,
):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-gems-tabular-scorer-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    if ground_truth_text is None:
        shutil.copy(FIXTURE_DIR / "hidden_labels.csv", input_dir / "ground_truth.csv")
    else:
        (input_dir / "ground_truth.csv").write_text(
            ground_truth_text,
            encoding="utf-8",
        )
    (input_dir / "submission.csv").write_text(submission_text, encoding="utf-8")
    (input_dir / "agora-runtime.json").write_text(
        json.dumps(runtime_config(id_column, value_column, metric)),
        encoding="utf-8",
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.RUNTIME_CONFIG_PATH = input_dir / "agora-runtime.json"
    module.GROUND_TRUTH_PATH = input_dir / "ground_truth.csv"
    module.SUBMISSION_PATH = input_dir / "submission.csv"
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    shutil.rmtree(workspace)
    return exit_code, payload


sample_submission = (FIXTURE_DIR / "sample_submission.csv").read_text(encoding="utf-8")
ground_truth = (FIXTURE_DIR / "hidden_labels.csv").read_text(encoding="utf-8")
custom_submission = sample_submission.replace("id,prediction", "sample_id,forecast")
exit_code, payload = run_case(custom_submission, "sample_id", "forecast")
assert exit_code == 0, f"custom column run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["details"]["matched_rows"] == 10, payload

partial_submission = "\n".join(sample_submission.strip().splitlines()[:-1]) + "\n"
exit_code, payload = run_case(partial_submission)
assert exit_code == 0, f"partial submission should be rejected as invalid, not crash: {exit_code}"
assert payload["ok"] is False, payload
assert "exactly one prediction row" in payload["error"], payload
assert payload["details"]["missing_ids"] > 0, payload

duplicate_submission = (
    sample_submission.strip() + "\n" + sample_submission.strip().splitlines()[1] + "\n"
)
exit_code, payload = run_case(duplicate_submission)
assert exit_code == 0, f"duplicate submission should be rejected as invalid, not crash: {exit_code}"
assert payload["ok"] is False, payload
assert "duplicate prediction ids" in payload["error"], payload
assert payload["details"]["duplicate_ids"] > 0, payload

nonnumeric_submission = sample_submission.replace("s4,12.3", "s4,not-a-number")
exit_code, payload = run_case(nonnumeric_submission)
assert exit_code == 0, f"nonnumeric submission should be rejected as invalid, not crash: {exit_code}"
assert payload["ok"] is False, payload
assert "non-numeric prediction values" in payload["error"], payload
assert payload["details"]["invalid_value_ids"] > 0, payload

perfect_rmse_submission = ground_truth.replace("label", "prediction")
exit_code, payload = run_case(perfect_rmse_submission, metric="rmse")
assert exit_code == 0, f"rmse run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["selected_metric"] == "rmse", payload
assert payload["details"]["selected_metric_value"] == 0.0, payload

classification_truth = "id,label\nrow-1,a\nrow-2,b\nrow-3,a\n"
classification_submission = "id,prediction\nrow-1,a\nrow-2,b\nrow-3,b\n"
exit_code, payload = run_case(
    classification_submission,
    metric="accuracy",
    ground_truth_text=classification_truth,
)
assert exit_code == 0, f"classification run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["details"]["accuracy"] == round(2 / 3, 12), payload

print("regression scorer runtime tests passed")
