import importlib.util
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "containers" / "gems-code-executor" / "score.py"


def load_executor_module():
    spec = importlib.util.spec_from_file_location("agora_code_executor", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load code executor module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_harness_bundle(path: Path, manifest: dict, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as archive:
      archive.writestr("agora-harness.json", json.dumps(manifest))
      for relative_path, content in files.items():
          archive.writestr(relative_path, content)


def run_case(runtime_config: dict, harness_manifest: dict, harness_files: dict[str, str], submission_source: str):
    module = load_executor_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-gems-code-executor-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    mount = runtime_config["mount"]
    harness_path = input_dir / mount["evaluation_bundle_name"]
    submission_path = input_dir / mount["submission_file_name"]
    write_harness_bundle(harness_path, harness_manifest, harness_files)
    submission_path.write_text(submission_source, encoding="utf-8")
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


runtime_config = {
    "version": "v1",
    "metric": "pass_rate",
    "mount": {
        "evaluation_bundle_name": "evaluation_bundle.zip",
        "submission_file_name": "submission.py",
    },
    "submission_contract": {
        "version": "v1",
        "kind": "opaque_file",
        "file": {
            "extension": ".py",
            "mime": "text/x-python",
            "max_bytes": 1024,
        },
    },
    "evaluation_contract": {
        "kind": "opaque_file",
        "file": {
            "extension": ".zip",
            "mime": "application/zip",
        },
    },
}

harness_manifest = {
    "version": "v1",
    "language": "python",
    "timeout_ms": 2000,
    "strip_trailing_whitespace": True,
    "tests": [
        {
            "name": "echo-alpha",
            "stdin_path": "tests/input_01.txt",
            "expected_stdout_path": "tests/output_01.txt",
        },
        {
            "name": "echo-beta",
            "stdin_path": "tests/input_02.txt",
            "expected_stdout_path": "tests/output_02.txt",
        },
    ],
}

harness_files = {
    "tests/input_01.txt": "alpha\n",
    "tests/output_01.txt": "alpha\n",
    "tests/input_02.txt": "beta\n",
    "tests/output_02.txt": "beta\n",
}

passing_submission = """
import sys

print(sys.stdin.read().strip())
"""

exit_code, payload = run_case(
    runtime_config,
    harness_manifest,
    harness_files,
    passing_submission,
)
assert exit_code == 0, f"pass-rate run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["comparison_kind"] == "execution_judge", payload
assert payload["details"]["tests_passed"] == 2, payload
assert payload["details"]["selected_metric"] == "pass_rate", payload

failing_submission = """
import sys

print(sys.stdin.read().strip().upper())
"""

exit_code, payload = run_case(
    runtime_config,
    harness_manifest,
    harness_files,
    failing_submission,
)
assert exit_code == 0, f"failing run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 0.0, payload
assert payload["details"]["tests_passed"] == 0, payload
assert payload["details"]["results"][0]["reason"] == "mismatch", payload

invalid_harness_manifest = {
    "version": "v1",
    "language": "python",
    "tests": [],
}

exit_code, payload = run_case(
    runtime_config,
    invalid_harness_manifest,
    {},
    passing_submission,
)
assert exit_code == 1, f"invalid harness should fail runtime: {exit_code}"
assert payload["ok"] is False, payload
assert "non-empty tests array" in payload["error"], payload

path_escape_manifest = {
    "version": "v1",
    "language": "python",
    "tests": [
        {
            "name": "escape",
            "stdin_path": "../escape.txt",
            "expected_stdout_path": "tests/output_01.txt",
        }
    ],
}

exit_code, payload = run_case(
    runtime_config,
    path_escape_manifest,
    harness_files,
    passing_submission,
)
assert exit_code == 1, f"path-escape harness should fail runtime: {exit_code}"
assert payload["ok"] is False, payload
assert "must not escape the harness root" in payload["error"], payload
