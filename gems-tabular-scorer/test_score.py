import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "gems-tabular-scorer" / "score.py"


def load_scorer_module():
    spec = importlib.util.spec_from_file_location("agora_regression_scorer", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load regression scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_config(id_column: str, value_column: str, metric: str = "r2") -> dict:
    return {
        "version": "v2",
        "metric": metric,
        "mount": {
            "evaluation_bundle_name": "evaluation",
            "submission_file_name": "submission",
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
    runtime_payload: dict | None = None,
):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-gems-tabular-scorer-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "evaluation").write_text(
        ground_truth_text
        if ground_truth_text is not None
        else "id,label\ns1,10.0\ns2,11.2\ns3,9.8\ns4,12.3\ns5,13.1\ns6,8.4\ns7,7.7\ns8,15.2\ns9,10.5\ns10,9.1\n",
        encoding="utf-8",
    )
    (input_dir / "submission").write_text(submission_text, encoding="utf-8")
    (input_dir / "agora-runtime.json").write_text(
        json.dumps(runtime_payload or runtime_config(id_column, value_column, metric)),
        encoding="utf-8",
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    shutil.rmtree(workspace)
    return exit_code, payload


sample_submission = """id,prediction
s1,10.0
s2,11.2
s3,9.8
s4,12.3
s5,13.1
s6,8.4
s7,7.7
s8,15.2
s9,10.5
s10,9.1
"""
ground_truth = """id,label
s1,10.0
s2,11.2
s3,9.8
s4,12.3
s5,13.1
s6,8.4
s7,7.7
s8,15.2
s9,10.5
s10,9.1
"""
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

legacy_runtime_payload = runtime_config("id", "prediction", "r2")
legacy_runtime_payload["version"] = "v1"
exit_code, payload = run_case(
    sample_submission,
    runtime_payload=legacy_runtime_payload,
)
assert exit_code == 1, f"legacy runtime version should fail loudly: {exit_code}"
assert payload["ok"] is False, payload
assert "Expected version=v2" in payload["error"], payload

old_mount_runtime_payload = runtime_config("id", "prediction", "r2")
old_mount_runtime_payload["mount"] = {
    "evaluation_bundle_name": "ground_truth.csv",
    "submission_file_name": "submission",
}
exit_code, payload = run_case(
    sample_submission,
    runtime_payload=old_mount_runtime_payload,
)
assert exit_code == 1, f"old mount names should fail loudly: {exit_code}"
assert payload["ok"] is False, payload
assert "evaluation_bundle_name must be evaluation" in payload["error"], payload

print("regression scorer runtime tests passed")
