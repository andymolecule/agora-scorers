import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "examples" / "external-weighted-composite" / "score.py"
COMMON_DIR = ROOT_DIR / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from runtime_test_support import (
    build_external_runtime_profile,
    read_score_output,
    stage_runtime_artifact,
    write_runtime_manifest,
)


def load_scorer_module():
    spec = importlib.util.spec_from_file_location(
        "agora_external_weighted_composite",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load external weighted composite scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_artifact_contract() -> dict:
    evaluation_slot = {
        "required": True,
        "description": "External scorer config",
        "file": {
            "extension": ".json",
            "mime_type": "application/json",
            "max_bytes": 4096,
        },
        "validator": {
            "kind": "json_document",
        },
    }
    submission_slot = {
        "required": True,
        "description": "External scorer submission payload",
        "file": {
            "extension": ".json",
            "mime_type": "application/json",
            "max_bytes": 4096,
        },
        "validator": {
            "kind": "json_document",
        },
    }
    return {
        "evaluation": [
            {
                **evaluation_slot,
                "role": "weights",
            },
            {
                **evaluation_slot,
                "role": "policy",
            },
        ],
        "submission": [
            {
                **submission_slot,
                "role": "metrics",
            },
            {
                **submission_slot,
                "role": "manifest",
            },
        ],
        "relations": [],
    }


def build_scorer_result_schema() -> dict:
    return {
        "dimensions": [
            "binding_score",
            "expression_score",
            "solubility_score",
        ],
        "bonuses": ["novelty_bonus"],
        "penalties": ["calibration_penalty"],
        "summary_fields": [
            {"key": "candidates_scored", "value_type": "integer"},
            {"key": "candidates_passing_threshold", "value_type": "integer"},
        ],
        "allow_additional_details": True,
    }


def run_case(*, weights_payload: str, policy_payload: str, metrics_payload: str, manifest_payload: str):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-external-weighted-composite-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    artifact_contract = build_artifact_contract()
    weights_artifact = stage_runtime_artifact(
        input_dir,
        lane="evaluation",
        role="weights",
        file_name="weights.json",
        payload=weights_payload,
        validator=artifact_contract["evaluation"][0]["validator"],
        mime_type="application/json",
    )
    policy_artifact = stage_runtime_artifact(
        input_dir,
        lane="evaluation",
        role="policy",
        file_name="policy.json",
        payload=policy_payload,
        validator=artifact_contract["evaluation"][1]["validator"],
        mime_type="application/json",
    )
    metrics_artifact = stage_runtime_artifact(
        input_dir,
        lane="submission",
        role="metrics",
        file_name="metrics.json",
        payload=metrics_payload,
        validator=artifact_contract["submission"][0]["validator"],
        mime_type="application/json",
    )
    manifest_artifact = stage_runtime_artifact(
        input_dir,
        lane="submission",
        role="manifest",
        file_name="manifest.json",
        payload=manifest_payload,
        validator=artifact_contract["submission"][1]["validator"],
        mime_type="application/json",
    )
    write_runtime_manifest(
        input_dir,
        runtime_profile=build_external_runtime_profile(),
        artifact_contract=artifact_contract,
        scorer_result_schema=build_scorer_result_schema(),
        artifacts=[
            weights_artifact,
            policy_artifact,
            metrics_artifact,
            manifest_artifact,
        ],
        objective="maximize",
        final_score_key="final_score",
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
        weights_payload=json.dumps(
            {
                "dimensions": {
                    "binding_score": 0.5,
                    "expression_score": 0.2,
                    "solubility_score": 0.15,
                },
                "bonuses": {
                    "novelty_bonus": 0.1,
                },
                "penalties": {
                    "calibration_penalty": 0.05,
                },
            }
        ),
        policy_payload=json.dumps(
            {
                "required_submission_roles": ["metrics", "manifest"],
                "candidate_count_field": "candidates_scored",
            }
        ),
        metrics_payload=json.dumps(
            {
                "binding_score": 0.92,
                "expression_score": 0.85,
                "solubility_score": 0.78,
                "novelty_bonus": 0.12,
                "calibration_penalty": 0.03,
            }
        ),
        manifest_payload=json.dumps(
            {
                "candidates_scored": 10,
                "candidates_passing_threshold": 7,
            }
        ),
    )
    assert exit_code == 0, payload
    assert payload["ok"] is True, payload
    assert round(payload["score"], 4) == 0.7575, payload
    assert payload["details"]["aggregation"] == "weighted_composite", payload
    assert payload["details"]["binding_score"] == 0.92, payload
    assert payload["details"]["candidates_scored"] == 10, payload
    assert payload["details"]["weights"]["binding_score"] == 0.5, payload

    exit_code, payload = run_case(
        weights_payload=json.dumps(
            {
                "dimensions": {
                    "binding_score": 0.5,
                    "expression_score": 0.2,
                    "solubility_score": 0.15,
                },
                "bonuses": {"novelty_bonus": 0.1},
                "penalties": {"calibration_penalty": 0.05},
            }
        ),
        policy_payload=json.dumps(
            {
                "required_submission_roles": ["metrics", "manifest"],
                "candidate_count_field": "candidates_scored",
            }
        ),
        metrics_payload=json.dumps(
            {
                "binding_score": 0.92,
                "expression_score": "bad-value",
                "solubility_score": 0.78,
                "novelty_bonus": 0.12,
                "calibration_penalty": 0.03,
            }
        ),
        manifest_payload=json.dumps(
            {
                "candidates_scored": 10,
                "candidates_passing_threshold": 7,
            }
        ),
    )
    assert exit_code == 0, payload
    assert payload["ok"] is False, payload
    assert "expression_score" in payload["error"], payload

    print("external weighted composite scorer tests passed")


if __name__ == "__main__":
    main()
