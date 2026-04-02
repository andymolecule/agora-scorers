import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "gems-match-scorer" / "score.py"


def load_scorer_module():
    spec = importlib.util.spec_from_file_location("agora_repro_scorer", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load reproducibility scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_input_file(path: Path, payload: str | bytes):
    if isinstance(payload, bytes):
        path.write_bytes(payload)
        return
    path.write_text(payload, encoding="utf-8")


def run_case(
    runtime_config: dict,
    evaluation_payload: str | bytes,
    submission_payload: str | bytes,
):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-gems-match-scorer-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    mount = runtime_config["mount"]
    write_input_file(input_dir / mount["evaluation_bundle_name"], evaluation_payload)
    write_input_file(input_dir / mount["submission_file_name"], submission_payload)
    (input_dir / "agora-runtime.json").write_text(
        json.dumps(runtime_config),
        encoding="utf-8",
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.RUNTIME_CONFIG_PATH = input_dir / "agora-runtime.json"
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    shutil.rmtree(workspace)
    return exit_code, payload


csv_runtime_config = {
    "version": "v2",
    "metric": "exact_match",
    "mount": {
        "evaluation_bundle_name": "evaluation",
        "submission_file_name": "submission",
    },
    "submission_contract": {
        "version": "v1",
        "kind": "csv_table",
        "file": {
            "extension": ".csv",
            "mime": "text/csv",
            "max_bytes": 1024,
        },
        "columns": {
            "required": ["id", "value"],
            "id": "id",
            "value": "value",
            "allow_extra": True,
        },
    },
}

exit_code, payload = run_case(
    csv_runtime_config,
    "id,value\nrow-1,1\nrow-2,2\n",
    "id,value\nrow-1,1\nrow-2,2\n",
)
assert exit_code == 0, f"csv exact-match run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["comparison_kind"] == "csv_table", payload

json_runtime_config = {
    "version": "v2",
    "metric": "exact_match",
    "mount": {
        "evaluation_bundle_name": "evaluation",
        "submission_file_name": "submission",
    },
    "submission_contract": {
        "version": "v1",
        "kind": "json_file",
        "file": {
            "extension": ".json",
            "mime": "application/json",
            "max_bytes": 1024,
        },
    },
}

exit_code, payload = run_case(
    json_runtime_config,
    # Object key order is intentionally irrelevant here. json.loads() normalizes
    # JSON objects into Python dicts, and exact-match compares the parsed value.
    '{"result":{"value":42,"status":"ok"}}',
    '{"result":{"status":"ok","value":42}}',
)
assert exit_code == 0, f"json exact-match run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["comparison_kind"] == "json_file", payload

exit_code, payload = run_case(
    json_runtime_config,
    '{"result":{"value":42,"status":"ok"}}',
    '{"result":{"status":"ok","value":43}}',
)
assert exit_code == 0, f"json mismatch run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 0.0, payload

structured_record_runtime_config = {
    "version": "v2",
    "metric": "validation_score",
    "mount": {
        "evaluation_bundle_name": "evaluation",
        "submission_file_name": "submission",
    },
    "submission_contract": {
        "version": "v1",
        "kind": "json_file",
        "file": {
            "extension": ".json",
            "mime": "application/json",
            "max_bytes": 1024,
        },
    },
}

exit_code, payload = run_case(
    structured_record_runtime_config,
    json.dumps(
        {
            "required_fields": [
                "incident_id",
                "severity",
                "timeline",
                "actions_taken",
            ],
            "non_empty_array_fields": ["timeline", "actions_taken"],
            "allowed_string_values": {
                "severity": ["low", "medium", "high"],
            },
        }
    ),
    json.dumps(
        {
            "incident_id": "INC-2042",
            "severity": "high",
            "timeline": [{"timestamp": "2026-03-01T10:00:00Z", "event": "alert"}],
            "actions_taken": ["isolated service"],
        }
    ),
)
assert (
    exit_code == 0
), f"structured-record validation run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["comparison_kind"] == "json_record", payload
assert payload["details"]["checks_passed"] == payload["details"]["checks_total"], payload

exit_code, payload = run_case(
    structured_record_runtime_config,
    json.dumps(
        {
            "required_fields": [
                "incident_id",
                "severity",
                "timeline",
                "actions_taken",
            ],
            "non_empty_array_fields": ["timeline", "actions_taken"],
            "allowed_string_values": {
                "severity": ["low", "medium", "high"],
            },
        }
    ),
    json.dumps(
        {
            "incident_id": "INC-2042",
            "severity": "critical",
            "actions_taken": [],
        }
    ),
)
assert (
    exit_code == 0
), f"structured-record invalid run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] < 0.5, payload
assert "missing_or_empty:timeline" in payload["details"]["failed_checks"], payload
assert "array_required:actions_taken" in payload["details"]["failed_checks"], payload
assert "allowed_value:severity" in payload["details"]["failed_checks"], payload

opaque_runtime_config = {
    "version": "v2",
    "metric": "exact_match",
    "mount": {
        "evaluation_bundle_name": "evaluation",
        "submission_file_name": "submission",
    },
    "submission_contract": {
        "version": "v1",
        "kind": "opaque_file",
        "file": {
            "extension": ".pdf",
            "mime": "application/pdf",
            "max_bytes": 1024,
        },
    },
}

exit_code, payload = run_case(
    opaque_runtime_config,
    b"%PDF-1.7\nmock reference document\n",
    b"%PDF-1.7\nmock reference document\n",
)
assert exit_code == 0, f"opaque exact-match run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["comparison_kind"] == "opaque_file", payload

exit_code, payload = run_case(
    opaque_runtime_config,
    b"%PDF-1.7\nmock reference document\n",
    b"%PDF-1.7\nchanged solver document\n",
)
assert exit_code == 0, f"opaque mismatch run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 0.0, payload

legacy_runtime_config = dict(csv_runtime_config)
legacy_runtime_config["version"] = "v1"
exit_code, payload = run_case(
    legacy_runtime_config,
    "id,value\nrow-1,1\nrow-2,2\n",
    "id,value\nrow-1,1\nrow-2,2\n",
)
assert exit_code == 1, f"legacy runtime version should fail loudly: {exit_code}"
assert payload["ok"] is False, payload
assert "Expected version=v2" in payload["error"], payload

old_mount_runtime_config = dict(csv_runtime_config)
old_mount_runtime_config["mount"] = {
    "evaluation_bundle_name": "ground_truth.csv",
    "submission_file_name": "submission",
}
exit_code, payload = run_case(
    old_mount_runtime_config,
    "id,value\nrow-1,1\nrow-2,2\n",
    "id,value\nrow-1,1\nrow-2,2\n",
)
assert exit_code == 1, f"old mount names should fail loudly: {exit_code}"
assert payload["ok"] is False, payload
assert "evaluation_bundle_name must be evaluation" in payload["error"], payload

print("repro scorer runtime tests passed")
