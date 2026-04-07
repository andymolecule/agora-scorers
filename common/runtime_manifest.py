import json
from pathlib import Path
from typing import Any, Callable

RUNTIME_MANIFEST_FILE_NAME = "runtime-manifest.json"

_COVERAGE_POLICIES = {"reject", "ignore", "penalize"}
_DUPLICATE_ID_POLICIES = {"reject", "ignore"}
_INVALID_VALUE_POLICIES = {"reject", "ignore"}
_COMPARATORS = {"maximize", "minimize"}


def _normalize_relative_path(value: Any, *, fail_runtime: Callable[[str], None]) -> Path:
    if not isinstance(value, str) or not value.strip():
        fail_runtime(
            "Runtime manifest present artifacts must include a non-empty relative_path."
        )

    normalized = value.replace("\\", "/").strip()
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        fail_runtime(
            f"Runtime manifest artifact path must stay within /input. Received: {value}"
        )

    return candidate


def _require_mapping(
    container: dict[str, Any],
    key: str,
    *,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        fail_runtime(f"Runtime manifest {key} must be an object.")
    return value


def _require_non_empty_string(
    container: dict[str, Any],
    key: str,
    *,
    fail_runtime: Callable[[str], None],
) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        fail_runtime(f"Runtime manifest {key} must be a non-empty string.")
    return value.strip()


def _require_list(
    container: dict[str, Any],
    key: str,
    *,
    fail_runtime: Callable[[str], None],
) -> list[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        fail_runtime(f"Runtime manifest {key} must be an array.")
    return value


def _require_enum_value(
    container: dict[str, Any],
    key: str,
    *,
    allowed_values: set[str],
    fail_runtime: Callable[[str], None],
) -> str:
    value = _require_non_empty_string(
        container,
        key,
        fail_runtime=fail_runtime,
    )
    if value not in allowed_values:
        fail_runtime(
            f"Unsupported {key} in runtime manifest. Expected one of {','.join(sorted(allowed_values))}."
        )
    return value


def _require_external_limits(
    scorer: dict[str, Any],
    *,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    limits = _require_mapping(scorer, "limits", fail_runtime=fail_runtime)
    memory = _require_non_empty_string(limits, "memory", fail_runtime=fail_runtime)
    cpus = _require_non_empty_string(limits, "cpus", fail_runtime=fail_runtime)
    pids = limits.get("pids")
    timeout_ms = limits.get("timeoutMs")
    if not isinstance(pids, int) or pids <= 0:
        fail_runtime("Runtime manifest scorer.limits.pids must be a positive integer.")
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        fail_runtime(
            "Runtime manifest scorer.limits.timeoutMs must be a positive integer."
        )
    return {
        "memory": memory,
        "cpus": cpus,
        "pids": pids,
        "timeoutMs": timeout_ms,
    }


def _require_runtime_scorer(
    runtime_manifest: dict[str, Any],
    *,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    scorer = _require_mapping(runtime_manifest, "scorer", fail_runtime=fail_runtime)
    kind = _require_enum_value(
        scorer,
        "kind",
        allowed_values={"official", "external"},
        fail_runtime=fail_runtime,
    )
    image = _require_non_empty_string(scorer, "image", fail_runtime=fail_runtime)

    normalized_scorer: dict[str, Any] = {
        "kind": kind,
        "image": image,
    }
    if kind == "official":
        normalized_scorer["id"] = _require_non_empty_string(
            scorer,
            "id",
            fail_runtime=fail_runtime,
        )
    else:
        normalized_scorer["limits"] = _require_external_limits(
            scorer,
            fail_runtime=fail_runtime,
        )

    return normalized_scorer


def load_runtime_manifest(
    *,
    input_dir: Path,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    runtime_manifest_path = input_dir / RUNTIME_MANIFEST_FILE_NAME
    if not runtime_manifest_path.exists():
        fail_runtime(f"Missing required file: {runtime_manifest_path}")

    try:
        runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail_runtime(
            f"Invalid runtime manifest JSON at {runtime_manifest_path}: {error.msg}"
        )

    if runtime_manifest.get("kind") != "runtime_manifest":
        fail_runtime(
            "Unsupported runtime manifest kind. Expected kind=runtime_manifest."
        )

    scorer = _require_runtime_scorer(
        runtime_manifest,
        fail_runtime=fail_runtime,
    )
    artifact_contract = _require_mapping(
        runtime_manifest,
        "artifact_contract",
        fail_runtime=fail_runtime,
    )
    evaluation_slots = _require_list(
        artifact_contract,
        "evaluation",
        fail_runtime=fail_runtime,
    )
    submission_slots = _require_list(
        artifact_contract,
        "submission",
        fail_runtime=fail_runtime,
    )
    artifacts = _require_list(
        runtime_manifest,
        "artifacts",
        fail_runtime=fail_runtime,
    )
    relations = artifact_contract.get("relations", [])
    if not isinstance(relations, list):
        fail_runtime("Runtime manifest artifact_contract.relations must be an array.")

    metric = _require_non_empty_string(
        runtime_manifest,
        "metric",
        fail_runtime=fail_runtime,
    )
    comparator = _require_enum_value(
        runtime_manifest,
        "comparator",
        allowed_values=_COMPARATORS,
        fail_runtime=fail_runtime,
    )

    evaluation_bindings = runtime_manifest.get("evaluation_bindings", [])
    if not isinstance(evaluation_bindings, list):
        fail_runtime("Runtime manifest evaluation_bindings must be an array.")

    scorer_result_schema = runtime_manifest.get("scorer_result_schema")
    if scorer_result_schema is not None and not isinstance(scorer_result_schema, dict):
        fail_runtime("Runtime manifest scorer_result_schema must be an object.")

    relation_plan = runtime_manifest.get("relation_plan")
    if relation_plan is not None and not isinstance(relation_plan, dict):
        fail_runtime("Runtime manifest relation_plan must be an object when present.")

    policies = _require_mapping(
        runtime_manifest,
        "policies",
        fail_runtime=fail_runtime,
    )
    coverage_policy = _require_enum_value(
        policies,
        "coverage_policy",
        allowed_values=_COVERAGE_POLICIES,
        fail_runtime=fail_runtime,
    )
    duplicate_id_policy = _require_enum_value(
        policies,
        "duplicate_id_policy",
        allowed_values=_DUPLICATE_ID_POLICIES,
        fail_runtime=fail_runtime,
    )
    invalid_value_policy = _require_enum_value(
        policies,
        "invalid_value_policy",
        allowed_values=_INVALID_VALUE_POLICIES,
        fail_runtime=fail_runtime,
    )

    return {
        "metric": metric,
        "comparator": comparator,
        "scorer": scorer,
        "artifact_contract": artifact_contract,
        "evaluation_slots": evaluation_slots,
        "submission_slots": submission_slots,
        "artifacts": artifacts,
        "relations": relations,
        "evaluation_bindings": evaluation_bindings,
        "relation_plan": relation_plan,
        "scorer_result_schema": scorer_result_schema,
        "policies": {
            "coverage_policy": coverage_policy,
            "duplicate_id_policy": duplicate_id_policy,
            "invalid_value_policy": invalid_value_policy,
        },
        "input_dir": input_dir,
        "runtime_manifest_path": runtime_manifest_path,
    }


def _find_slot(
    runtime_manifest: dict[str, Any],
    *,
    lane: str,
    role: str,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    slot_key = f"{lane}_slots"
    slots = runtime_manifest.get(slot_key)
    if not isinstance(slots, list):
        fail_runtime(f"Runtime manifest is missing {slot_key}.")

    slot = next(
        (
            candidate
            for candidate in slots
            if isinstance(candidate, dict) and candidate.get("role") == role
        ),
        None,
    )
    if slot is None:
        fail_runtime(f"Runtime manifest is missing {lane} slot role {role}.")

    return slot


def resolve_artifact_by_role(
    runtime_manifest: dict[str, Any],
    *,
    lane: str,
    role: str,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    slot = _find_slot(
        runtime_manifest,
        lane=lane,
        role=role,
        fail_runtime=fail_runtime,
    )

    artifacts = runtime_manifest.get("artifacts", [])
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("lane") == lane
        and artifact.get("role") == role
    ]
    if len(matches) != 1:
        fail_runtime(
            f"Runtime manifest must contain exactly one {lane} artifact entry for role {role}."
        )

    artifact = matches[0]
    if artifact.get("validator", {}).get("kind") != slot.get("validator", {}).get("kind"):
        fail_runtime(
            f"Runtime manifest artifact {lane}.{role} validator does not match the declared slot validator."
        )

    slot_required = bool(slot.get("required", False))
    artifact_present = bool(artifact.get("present", False))
    if slot_required and not artifact_present:
        fail_runtime(f"Missing required {lane} artifact role {role}.")
    if not artifact_present:
        return {
            "role": role,
            "slot": slot,
            "artifact": artifact,
            "path": None,
        }

    relative_path = _normalize_relative_path(
        artifact.get("relative_path"),
        fail_runtime=fail_runtime,
    )
    artifact_path = runtime_manifest["input_dir"] / relative_path
    if not artifact_path.exists():
        fail_runtime(
            f"Runtime manifest artifact path does not exist for {lane}.{role}: {artifact_path}"
        )

    return {
        "role": role,
        "slot": slot,
        "artifact": artifact,
        "path": artifact_path,
    }
