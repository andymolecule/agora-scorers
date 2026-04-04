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
    evaluation_bindings = _require_list(
        runtime_manifest,
        "evaluation_bindings",
        fail_runtime=fail_runtime,
    )
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
        "artifact_contract": artifact_contract,
        "evaluation_slots": evaluation_slots,
        "submission_slots": submission_slots,
        "artifacts": artifacts,
        "evaluation_bindings": evaluation_bindings,
        "policies": {
            "coverage_policy": coverage_policy,
            "duplicate_id_policy": duplicate_id_policy,
            "invalid_value_policy": invalid_value_policy,
        },
        "input_dir": input_dir,
        "runtime_manifest_path": runtime_manifest_path,
    }


def find_relation(
    runtime_manifest: dict[str, Any],
    *,
    kind: str,
    **expected_fields: str,
) -> dict[str, Any] | None:
    artifact_contract = runtime_manifest.get("artifact_contract", {})
    if not isinstance(artifact_contract, dict):
        return None
    relations = artifact_contract.get("relations", [])
    if not isinstance(relations, list):
        return None
    for relation in relations:
        if not isinstance(relation, dict) or relation.get("kind") != kind:
            continue
        if all(relation.get(field) == value for field, value in expected_fields.items()):
            return relation
    return None


def require_relation(
    runtime_manifest: dict[str, Any],
    *,
    kind: str,
    fail_runtime: Callable[[str], None],
    **expected_fields: str,
) -> dict[str, Any]:
    relation = find_relation(
        runtime_manifest,
        kind=kind,
        **expected_fields,
    )
    if relation is not None:
        return relation

    expected = ", ".join(f"{field}={value}" for field, value in expected_fields.items())
    fail_runtime(
        f"Runtime manifest is missing relation kind={kind} with {expected}."
    )


def resolve_runtime_artifact(
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
        "slot": slot,
        "artifact": artifact,
        "path": artifact_path,
    }
