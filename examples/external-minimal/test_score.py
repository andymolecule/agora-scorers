import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "examples" / "external-minimal" / "score.py"
COMMON_DIR = ROOT_DIR / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from runtime_test_support import (
    build_external_scorer,
    read_score_output,
    stage_runtime_artifact,
    write_runtime_manifest,
)


def load_scorer_module():
    spec = importlib.util.spec_from_file_location("agora_external_minimal", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load external minimal scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_artifact_contract() -> dict:
    return {
        "evaluation": [
            {
                "role": "rubric",
                "required": True,
                "description": "Expected submission fields",
                "file": {
                    "extension": ".json",
                    "mime_type": "application/json",
                    "max_bytes": 4096,
                },
                "validator": {
                    "kind": "json_document",
                },
            }
        ],
        "submission": [
            {
                "role": "candidate",
                "required": True,
                "description": "Submitted candidate payload",
                "file": {
                    "extension": ".json",
                    "mime_type": "application/json",
                    "max_bytes": 4096,
                },
                "validator": {
                    "kind": "json_document",
                },
            }
        ],
        "relations": [],
    }


def build_scorer_result_schema() -> dict:
    return {
        "dimensions": ["correctness_score"],
        "summary_fields": [
            {"key": "matched_fields", "value_type": "integer"},
            {"key": "evaluated_fields", "value_type": "integer"},
        ],
        "allow_additional_details": True,
    }


def run_case(*, rubric_payload: str, submission_payload: str):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-external-minimal-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    artifact_contract = build_artifact_contract()
    rubric_artifact = stage_runtime_artifact(
        input_dir,
        lane="evaluation",
        role="rubric",
        file_name="rubric.json",
        payload=rubric_payload,
        validator=artifact_contract["evaluation"][0]["validator"],
        mime_type="application/json",
    )
    candidate_artifact = stage_runtime_artifact(
        input_dir,
        lane="submission",
        role="candidate",
        file_name="candidate.json",
        payload=submission_payload,
        validator=artifact_contract["submission"][0]["validator"],
        mime_type="application/json",
    )
    write_runtime_manifest(
        input_dir,
        scorer=build_external_scorer(),
        metric="custom_correctness",
        comparator="maximize",
        artifact_contract=artifact_contract,
        scorer_result_schema=build_scorer_result_schema(),
        artifacts=[rubric_artifact, candidate_artifact],
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = read_score_output(output_dir)
    shutil.rmtree(workspace)
    return exit_code, payload


def main() -> None:
    exit_code, payload = run_case(
        rubric_payload=json.dumps({"expected_fields": {"id": "pep-1", "tier": "A"}}),
        submission_payload=json.dumps({"id": "pep-1", "tier": "A"}),
    )
    assert exit_code == 0, payload
    assert payload["ok"] is True, payload
    assert payload["score"] == 1.0, payload
    assert payload["details"]["matched_fields"] == 2, payload
    assert payload["details"]["evaluated_fields"] == 2, payload

    exit_code, payload = run_case(
        rubric_payload=json.dumps({"expected_fields": {"id": "pep-1", "tier": "A"}}),
        submission_payload=json.dumps({"id": "pep-1", "tier": "B"}),
    )
    assert exit_code == 0, payload
    assert payload["ok"] is True, payload
    assert payload["score"] == 0.5, payload
    assert payload["details"]["mismatched_fields"] == ["tier"], payload

    print("external minimal scorer tests passed")


if __name__ == "__main__":
    main()
