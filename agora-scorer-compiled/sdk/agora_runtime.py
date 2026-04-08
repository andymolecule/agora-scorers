import json
import os
from pathlib import Path
from typing import Any, Callable

from runtime_manifest import (
    load_runtime_manifest,
    resolve_artifact_by_role,
    resolve_program_scoring_asset,
    resolve_scoring_asset_by_role,
)

INPUT_ROOT = Path(os.environ.get("AGORA_RUNTIME_INPUT_ROOT", "/input"))
OUTPUT_ROOT = Path(os.environ.get("AGORA_RUNTIME_OUTPUT_ROOT", "/output"))
OUTPUT_PATH = OUTPUT_ROOT / "score.json"


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def write_score(
    *,
    score: float,
    details: dict[str, Any] | None = None,
    ok: bool = True,
    error: str | None = None,
) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": bool(ok),
        "score": float(score),
        "details": details or {},
    }
    if error is not None:
        payload["error"] = error
    OUTPUT_PATH.write_text(_serialize_payload(payload), encoding="utf-8")


def fail_runtime(message: str) -> None:
    write_score(score=0.0, details={}, ok=False, error=message)
    raise SystemExit(1)


def reject_submission(
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    write_score(score=0.0, details=details or {}, ok=False, error=message)
    raise SystemExit(0)


def load_runtime_context(
    *,
    input_dir: Path | None = None,
    fail_runtime_handler: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    fail_handler = fail_runtime_handler or fail_runtime
    runtime_manifest = load_runtime_manifest(
        input_dir=input_dir or INPUT_ROOT,
        fail_runtime=fail_handler,
    )
    runtime_manifest["program_asset"] = resolve_program_scoring_asset(
        runtime_manifest,
        fail_runtime=fail_handler,
        supported_abi_versions={"python-v1"},
    )
    return runtime_manifest


def resolve_evaluation_artifact(
    runtime_context: dict[str, Any],
    role: str,
    *,
    fail_runtime_handler: Callable[[str], None] | None = None,
) -> Path:
    fail_handler = fail_runtime_handler or fail_runtime
    artifact = resolve_artifact_by_role(
        runtime_context,
        lane="evaluation",
        role=role,
        fail_runtime=fail_handler,
    )
    if artifact["path"] is None:
        fail_handler(f"Missing required evaluation artifact for role {role}.")
    return artifact["path"]


def resolve_submission_artifact(
    runtime_context: dict[str, Any],
    role: str,
    *,
    fail_runtime_handler: Callable[[str], None] | None = None,
) -> Path:
    fail_handler = fail_runtime_handler or fail_runtime
    artifact = resolve_artifact_by_role(
        runtime_context,
        lane="submission",
        role=role,
        fail_runtime=fail_handler,
    )
    if artifact["path"] is None:
        reject_submission(f"Missing required submission artifact for role {role}.")
    return artifact["path"]


def resolve_scoring_asset(
    runtime_context: dict[str, Any],
    role: str,
    *,
    kind: str | None = None,
    fail_runtime_handler: Callable[[str], None] | None = None,
) -> Path:
    fail_handler = fail_runtime_handler or fail_runtime
    asset = resolve_scoring_asset_by_role(
        runtime_context,
        role=role,
        kind=kind,
        fail_runtime=fail_handler,
    )
    return asset["path"]


def load_json_file(path: Path, *, label: str | None = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        human_label = label or str(path)
        raise RuntimeError(f"{human_label} is not valid JSON: {error.msg}") from error


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")
