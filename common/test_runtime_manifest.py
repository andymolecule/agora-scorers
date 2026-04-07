import shutil
import tempfile
from pathlib import Path

from official_relation_plan import (
    aggregate_relation_scores,
    require_relation_plan_template,
    resolve_relation_artifact_sets,
)
from runtime_manifest import load_runtime_manifest, resolve_artifact_by_role
from runtime_test_support import (
    build_external_scorer,
    build_official_scorer,
    stage_runtime_artifact,
    write_runtime_manifest,
)


def fail_runtime(message: str) -> None:
    raise RuntimeError(message)


def build_artifact_contract() -> dict:
    return {
        "evaluation": [
            {
                "role": "reference",
                "required": True,
                "description": "Hidden truth bundle",
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
                "description": "Solver candidate bundle",
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
        "relations": [
            {
                "kind": "exact_match",
                "evaluation_role": "reference",
                "submission_role": "candidate",
            }
        ],
    }


def build_relation_plan() -> dict:
    return {
        "templates": [
            {
                "kind": "exact_match",
                "cardinality": "single",
                "aggregation": "single",
                "evaluation": [
                    {
                        "acceptedValidatorKinds": ["json_document"],
                        "requiredFile": {
                            "extension": ".json",
                            "mimeType": "application/json",
                        },
                    }
                ],
                "submission": [
                    {
                        "acceptedValidatorKinds": ["json_document"],
                        "requiredFile": {
                            "extension": ".json",
                            "mimeType": "application/json",
                        },
                    }
                ],
            }
        ]
    }


def make_runtime_manifest(*, scorer: dict, relation_plan: dict | None) -> dict:
    workspace = Path(tempfile.mkdtemp(prefix="agora-runtime-manifest-test-"))
    input_dir = workspace / "input"
    input_dir.mkdir()

    artifact_contract = build_artifact_contract()
    reference_artifact = stage_runtime_artifact(
        input_dir,
        lane="evaluation",
        role="reference",
        file_name="reference.json",
        payload='{"score": 1}',
        validator=artifact_contract["evaluation"][0]["validator"],
        mime_type="application/json",
    )
    candidate_artifact = stage_runtime_artifact(
        input_dir,
        lane="submission",
        role="candidate",
        file_name="candidate.json",
        payload='{"score": 1}',
        validator=artifact_contract["submission"][0]["validator"],
        mime_type="application/json",
    )

    runtime_manifest = write_runtime_manifest(
        input_dir,
        scorer=scorer,
        metric="exact_match",
        comparator="maximize",
        artifact_contract=artifact_contract,
        relation_plan=relation_plan,
        artifacts=[reference_artifact, candidate_artifact],
    )
    runtime_manifest["workspace"] = workspace
    return runtime_manifest


def test_external_runtime_manifest_support() -> None:
    runtime_fixture = make_runtime_manifest(
        scorer=build_external_scorer(),
        relation_plan=None,
    )
    workspace = runtime_fixture["workspace"]
    try:
        runtime_manifest = load_runtime_manifest(
            input_dir=workspace / "input",
            fail_runtime=fail_runtime,
        )
        assert runtime_manifest["scorer"]["kind"] == "external"
        assert runtime_manifest["relation_plan"] is None
        assert runtime_manifest["scorer"]["limits"]["timeoutMs"] == 30_000

        reference_artifact = resolve_artifact_by_role(
            runtime_manifest,
            lane="evaluation",
            role="reference",
            fail_runtime=fail_runtime,
        )
        candidate_artifact = resolve_artifact_by_role(
            runtime_manifest,
            lane="submission",
            role="candidate",
            fail_runtime=fail_runtime,
        )
        assert reference_artifact["path"] is not None
        assert candidate_artifact["path"] is not None

        try:
            require_relation_plan_template(
                runtime_manifest,
                kind="exact_match",
                fail_runtime=fail_runtime,
            )
        except RuntimeError as error:
            assert "scorer.kind=official" in str(error)
        else:
            raise AssertionError("Expected official relation helpers to reject external scorers.")
    finally:
        shutil.rmtree(workspace)


def test_official_relation_plan_support() -> None:
    runtime_fixture = make_runtime_manifest(
        scorer=build_official_scorer("official_exact_match"),
        relation_plan=build_relation_plan(),
    )
    workspace = runtime_fixture["workspace"]
    try:
        runtime_manifest = load_runtime_manifest(
            input_dir=workspace / "input",
            fail_runtime=fail_runtime,
        )
        template = require_relation_plan_template(
            runtime_manifest,
            kind="exact_match",
            fail_runtime=fail_runtime,
        )
        relation_sets = resolve_relation_artifact_sets(
            runtime_manifest,
            template=template,
            fail_runtime=fail_runtime,
        )

        assert template["aggregation"] == "single"
        assert len(relation_sets) == 1
        assert relation_sets[0]["evaluation"][0]["role"] == "reference"
        assert relation_sets[0]["submission"][0]["role"] == "candidate"
        assert aggregate_relation_scores(
            [1.0],
            aggregation=template["aggregation"],
            fail_runtime=fail_runtime,
        ) == 1.0
    finally:
        shutil.rmtree(workspace)


def main() -> None:
    test_external_runtime_manifest_support()
    test_official_relation_plan_support()
    print("runtime manifest tests passed")


if __name__ == "__main__":
    main()
