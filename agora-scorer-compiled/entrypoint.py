import json
import os
import subprocess
import sys
from pathlib import Path

SCORER_REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_DIR = SCORER_REPO_ROOT / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from runtime_manifest import load_runtime_manifest, resolve_program_scoring_asset

INPUT_DIR = Path("/input")
OUTPUT_DIR = Path("/output")
OUTPUT_PATH = OUTPUT_DIR / "score.json"
SUPPORTED_OFFICIAL_PROFILE_ID = "official_compiled_runtime"
SUPPORTED_PROGRAM_ABI_VERSIONS = {"python-v1"}


def write_result(payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def fail_runtime(message: str) -> None:
    write_result({"ok": False, "score": 0.0, "error": message, "details": {}})
    raise SystemExit(1)


def require_official_runtime(runtime_manifest: dict) -> None:
    runtime_profile = runtime_manifest["runtime_profile"]
    if runtime_profile["kind"] != "official":
        fail_runtime(
            "agora-scorer-compiled requires runtime_profile.kind=official. Next step: run this image only for the official compiled runtime lane."
        )
    if runtime_profile["profile_id"] != SUPPORTED_OFFICIAL_PROFILE_ID:
        fail_runtime(
            f"agora-scorer-compiled only supports runtime_profile.profile_id={SUPPORTED_OFFICIAL_PROFILE_ID}."
        )


def build_program_env(runtime_manifest: dict, program_asset: dict) -> dict[str, str]:
    python_path_entries = [
        str(COMMON_DIR),
        str(SCORER_REPO_ROOT / "agora-scorer-compiled"),
        str(SCORER_REPO_ROOT / "agora-scorer-compiled" / "sdk"),
    ]
    existing_python_path = os.environ.get("PYTHONPATH", "").strip()
    if existing_python_path:
        python_path_entries.append(existing_python_path)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = ":".join(python_path_entries)
    environment["AGORA_RUNTIME_MANIFEST_PATH"] = str(
        runtime_manifest["runtime_manifest_path"]
    )
    environment["AGORA_RUNTIME_INPUT_ROOT"] = str(INPUT_DIR)
    environment["AGORA_RUNTIME_OUTPUT_ROOT"] = str(OUTPUT_DIR)
    environment["AGORA_RUNTIME_EVALUATION_ROOT"] = str(
        runtime_manifest["evaluation_root"]
    )
    environment["AGORA_RUNTIME_SUBMISSION_ROOT"] = str(
        runtime_manifest["submission_root"]
    )
    environment["AGORA_RUNTIME_SCORING_ASSETS_ROOT"] = str(
        runtime_manifest["scoring_assets_root"]
    )
    environment["AGORA_RUNTIME_PROFILE_ID"] = runtime_manifest["runtime_profile"][
        "profile_id"
    ]
    environment["AGORA_RUNTIME_OBJECTIVE"] = runtime_manifest["objective"]
    environment["AGORA_RUNTIME_FINAL_SCORE_KEY"] = runtime_manifest["final_score_key"]
    environment["AGORA_RUNTIME_PROGRAM_ROLE"] = program_asset["role"]
    environment["AGORA_RUNTIME_PROGRAM_ABI"] = program_asset["asset"]["abi_version"]
    return environment


def main() -> None:
    runtime_manifest = load_runtime_manifest(
        input_dir=INPUT_DIR,
        fail_runtime=fail_runtime,
    )
    require_official_runtime(runtime_manifest)
    program_asset = resolve_program_scoring_asset(
        runtime_manifest,
        fail_runtime=fail_runtime,
        supported_abi_versions=SUPPORTED_PROGRAM_ABI_VERSIONS,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(
        [sys.executable, str(program_asset["path"])],
        cwd=str(program_asset["path"].parent),
        env=build_program_env(runtime_manifest, program_asset),
        check=False,
    )
    if run.returncode != 0:
        raise SystemExit(run.returncode)

    if not OUTPUT_PATH.exists():
        fail_runtime(
            "Compiled program exited without writing /output/score.json. Next step: make the staged program write one deterministic score.json and retry."
        )


if __name__ == "__main__":
    main()
