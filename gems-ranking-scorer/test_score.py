import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "containers" / "gems-ranking-scorer" / "score.py"


def load_scorer_module():
    spec = importlib.util.spec_from_file_location("agora_ranking_scorer", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ranking scorer module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_config(metric: str = "spearman") -> dict:
    return {
        "version": "v1",
        "template": "official_table_metric_v1",
        "metric": metric,
        "mount": {
            "evaluation_bundle_name": "ground_truth.csv",
            "submission_file_name": "submission.csv",
        },
        "submission_contract": {
            "version": "v1",
            "kind": "csv_table",
            "columns": {
                "required": ["id", "score"],
                "id": "id",
                "value": "score",
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


def docking_runtime_config(metric: str = "spearman") -> dict:
    return {
        "version": "v1",
        "template": "official_table_metric_v1",
        "metric": metric,
        "mount": {
            "evaluation_bundle_name": "ground_truth.csv",
            "submission_file_name": "submission.csv",
        },
        "submission_contract": {
            "version": "v1",
            "kind": "csv_table",
            "columns": {
                "required": ["ligand_id", "docking_score"],
                "id": "ligand_id",
                "value": "docking_score",
                "allow_extra": True,
            },
        },
        "evaluation_contract": {
            "kind": "csv_table",
            "columns": {
                "required": ["ligand_id", "reference_score"],
                "id": "ligand_id",
                "value": "reference_score",
                "allow_extra": True,
            },
        },
        "policies": {
            "coverage_policy": "reject",
            "duplicate_id_policy": "reject",
            "invalid_value_policy": "reject",
        },
    }


def run_case(submission_text: str, ground_truth_text: str, metric: str = "spearman"):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-ranking-scorer-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "ground_truth.csv").write_text(ground_truth_text, encoding="utf-8")
    (input_dir / "submission.csv").write_text(submission_text, encoding="utf-8")
    (input_dir / "agora-runtime.json").write_text(
        json.dumps(runtime_config(metric)),
        encoding="utf-8",
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.RUNTIME_CONFIG_PATH = input_dir / "agora-runtime.json"
    module.GROUND_TRUTH_PATH = input_dir / "ground_truth.csv"
    module.SUBMISSION_PATH = input_dir / "submission.csv"
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    shutil.rmtree(workspace)
    return exit_code, payload


def run_docking_case(
    submission_text: str, ground_truth_text: str, metric: str = "spearman"
):
    module = load_scorer_module()
    workspace = Path(tempfile.mkdtemp(prefix="agora-gems-ranking-scorer-"))
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "ground_truth.csv").write_text(ground_truth_text, encoding="utf-8")
    (input_dir / "submission.csv").write_text(submission_text, encoding="utf-8")
    (input_dir / "agora-runtime.json").write_text(
        json.dumps(docking_runtime_config(metric)),
        encoding="utf-8",
    )

    module.INPUT_DIR = input_dir
    module.OUTPUT_DIR = output_dir
    module.RUNTIME_CONFIG_PATH = input_dir / "agora-runtime.json"
    module.GROUND_TRUTH_PATH = input_dir / "ground_truth.csv"
    module.SUBMISSION_PATH = input_dir / "submission.csv"
    module.OUTPUT_PATH = output_dir / "score.json"

    exit_code = 0
    try:
        module.main()
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    payload = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    shutil.rmtree(workspace)
    return exit_code, payload


ground_truth = "id,label\na,3\nb,2\nc,1\n"
perfect_submission = "id,score\na,3\nb,2\nc,1\n"
exit_code, payload = run_case(perfect_submission, ground_truth, metric="spearman")
assert exit_code == 0, f"perfect spearman run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["selected_metric"] == "spearman", payload

exit_code, payload = run_case(perfect_submission, ground_truth, metric="ndcg")
assert exit_code == 0, f"perfect ndcg run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["score"] == 1.0, payload
assert payload["details"]["selected_metric"] == "ndcg", payload

partial_submission = "id,score\na,3\nb,2\n"
exit_code, payload = run_case(partial_submission, ground_truth, metric="spearman")
assert exit_code == 0, f"partial ranking run should be rejected as invalid, not crash: {exit_code}"
assert payload["ok"] is False, payload
assert "exactly one ranking row" in payload["error"], payload

docking_ground_truth = "ligand_id,reference_score\nlig1,-7.3\nlig2,-8.1\n"
docking_submission = "ligand_id,docking_score\nlig1,-7.1\nlig2,-8.0\n"
exit_code, payload = run_docking_case(
    docking_submission, docking_ground_truth, metric="spearman"
)
assert exit_code == 0, f"docking run should not crash: {exit_code}"
assert payload["ok"] is True, payload
assert payload["details"]["selected_metric"] == "spearman", payload

print("ranking scorer runtime tests passed")
