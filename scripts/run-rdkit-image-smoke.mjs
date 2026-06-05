import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const rootDir = process.cwd();
const defaultImage = "agora-scorer-rdkit-smoke:local";
const requestedImage = process.env.AGORA_RDKIT_RUNTIME_IMAGE?.trim();
const image = requestedImage || defaultImage;

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({
        code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    });
  });
}

async function checkedRun(command, args, options = {}) {
  const result = await runCommand(command, args, options);
  if (result.code !== 0) {
    throw new Error(
      [
        `${command} ${args.join(" ")} failed with exit ${result.code}.`,
        result.stdout.trim() ? `stdout:\n${result.stdout.trim()}` : null,
        result.stderr.trim() ? `stderr:\n${result.stderr.trim()}` : null,
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  return result;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function writePayload(filePath, payload) {
  const bytes = Buffer.from(payload, "utf8");
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, bytes);
  return {
    size_bytes: bytes.length,
    sha256: sha256(bytes),
  };
}

function sdkSource() {
  return String.raw`
import json
import os
from pathlib import Path

from runtime_manifest import load_runtime_manifest, resolve_artifact_by_role


def _output_path():
    return Path(os.environ["AGORA_RUNTIME_OUTPUT_ROOT"]) / "score.json"


def _write_payload(payload):
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def fail_runtime(message, *, details=None):
    _write_payload({"ok": False, "score": 0.0, "error": message, "details": details or {}})
    raise SystemExit(1)


def write_score(*, score, details=None):
    _write_payload({"ok": True, "score": score, "details": details or {}})


def load_runtime_context():
    return load_runtime_manifest(
        input_dir=Path(os.environ["AGORA_RUNTIME_INPUT_ROOT"]),
        fail_runtime=fail_runtime,
    )


def resolve_submission_artifact(runtime_context, role):
    return resolve_artifact_by_role(
        runtime_context,
        lane="submission",
        role=role,
        fail_runtime=fail_runtime,
    )["path"]


def load_json_file(path, *, label="JSON file"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail_runtime(f"{label} is not valid JSON: {exc}")
`.trim();
}

function rdkitProgramSource() {
  return String.raw`
import csv
import hashlib
import math
import os
import subprocess
import tempfile
from pathlib import Path

from agora_runtime import load_json_file, load_runtime_context, resolve_submission_artifact, write_score
from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors
import joblib
import pandas
import scipy
import xgboost


OPENSOL_MODEL_SHA256 = "bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run_opensol_smoke(smiles):
    opensol_home = Path(os.environ["OPENSOL_HOME"])
    opensol_script = opensol_home / "Scripts" / "solubility_model.py"
    opensol_model = opensol_home / "Models" / "xgboost_rdkit_2d_clustering_model.json"
    assert _sha256(opensol_model) == OPENSOL_MODEL_SHA256

    with tempfile.TemporaryDirectory(prefix="opensol-smoke-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        input_csv = tmpdir_path / "input.csv"
        output_csv = tmpdir_path / "output.csv"
        input_csv.write_text(
            "SMILES,knn_mean,knn_max\n" + smiles + ",0.0,0.0\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                "python",
                str(opensol_script),
                "-j",
                "Prediction",
                "-m",
                "xgboost",
                "-dscr",
                "rdkit_2d",
                "-s",
                "clustering",
                "-i",
                str(input_csv),
                "-o",
                str(output_csv),
                "-c",
                "False",
            ],
            cwd=str(opensol_home / "Scripts"),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "OpenSOL smoke failed with exit "
                + str(completed.returncode)
                + "\nstdout:\n"
                + completed.stdout
                + "\nstderr:\n"
                + completed.stderr
            )
        with output_csv.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1
        log_s = float(rows[0]["xgboost_logS"])
        assert math.isfinite(log_s)
        return round(log_s, 6)


runtime_context = load_runtime_context()
payload = load_json_file(resolve_submission_artifact(runtime_context, "molecules"))
smiles = payload["smiles"]
ethanol = Chem.MolFromSmiles(smiles[0])
benzene = Chem.MolFromSmiles(smiles[1])
assert ethanol is not None and benzene is not None
benzene_bits = rdMolDescriptors.GetMorganFingerprintAsBitVect(benzene, 2, nBits=128).GetNumOnBits()
opensol_ethanol_log_s = _run_opensol_smoke(Chem.MolToSmiles(ethanol, canonical=True, isomericSmiles=True))
details = {
    "final_score": 1.0,
    "runtime_profile_id": os.environ["AGORA_RUNTIME_PROFILE_ID"],
    "rdkit_version": rdBase.rdkitVersion,
    "xgboost_version": xgboost.__version__,
    "pandas_version": pandas.__version__,
    "scipy_version": scipy.__version__,
    "joblib_version": joblib.__version__,
    "opensol_model_sha256": OPENSOL_MODEL_SHA256,
    "opensol_ethanol_log_s": opensol_ethanol_log_s,
    "ethanol_canonical_smiles": Chem.MolToSmiles(ethanol),
    "ethanol_heavy_atoms": ethanol.GetNumHeavyAtoms(),
    "ethanol_mol_wt": round(Descriptors.MolWt(ethanol), 3),
    "benzene_morgan_bits": benzene_bits,
    "contains_hydroxyl": bool(ethanol.HasSubstructMatch(Chem.MolFromSmarts("[OX2H]"))),
}
write_score(score=1.0, details=details)
`.trim();
}

async function stageSmokeWorkspace(workspace, runtimeImage) {
  const inputDir = path.join(workspace, "input");
  const outputDir = path.join(workspace, "output");
  const outputPath = path.join(outputDir, "score.json");
  await fs.mkdir(inputDir, { recursive: true });
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(outputPath, "");
  await fs.chmod(outputPath, 0o666);

  const moleculesPayload = JSON.stringify({ smiles: ["CCO", "c1ccccc1"] });
  const moleculesStats = await writePayload(
    path.join(inputDir, "submission", "molecules", "molecules.json"),
    moleculesPayload,
  );
  const programStats = await writePayload(
    path.join(inputDir, "scoring_assets", "compiled_program", "score.py"),
    rdkitProgramSource(),
  );
  const sdkStats = await writePayload(
    path.join(inputDir, "scoring_assets", "python_v1_runtime_sdk", "agora_runtime.py"),
    sdkSource(),
  );

  const artifactContract = {
    evaluation: [],
    submission: [
      {
        role: "molecules",
        required: true,
        description: "Small deterministic SMILES payload",
        file: {
          extension: ".json",
          mime_type: "application/json",
          max_bytes: 4096,
        },
        validator: {
          kind: "json_document",
        },
      },
    ],
    relations: [],
  };
  const runtimeManifest = {
    kind: "runtime_manifest",
    runtime_profile: {
      kind: "official",
      profile_id: "rdkit_python_runtime",
      image: runtimeImage,
      limits: {
        memory: "2g",
        cpus: "2",
        pids: 64,
        timeoutMs: 600000,
      },
      supported_program_abi_versions: ["python-v1"],
      determinism_env: {
        LANG: "C.UTF-8",
        LC_ALL: "C.UTF-8",
        PYTHONHASHSEED: "0",
        SOURCE_DATE_EPOCH: "0",
        TZ: "UTC",
      },
    },
    artifact_contract: artifactContract,
    evaluation_bindings: [],
    artifacts: [
      {
        lane: "submission",
        role: "molecules",
        required: true,
        present: true,
        validator: artifactContract.submission[0].validator,
        relative_path: "submission/molecules/molecules.json",
        file_name: "molecules.json",
        mime_type: "application/json",
        ...moleculesStats,
      },
    ],
    scoring_assets: [
      {
        role: "compiled_program",
        kind: "program",
        artifact_id: "score.py",
        relative_path: "scoring_assets/compiled_program/score.py",
        file_name: "score.py",
        abi_version: "python-v1",
        entrypoint: "score.py",
        ...programStats,
      },
      {
        role: "python_v1_runtime_sdk",
        kind: "document",
        artifact_id: "agora_runtime.py",
        relative_path: "scoring_assets/python_v1_runtime_sdk/agora_runtime.py",
        file_name: "agora_runtime.py",
        ...sdkStats,
      },
    ],
    objective: "maximize",
    final_score_key: "final_score",
    scorer_result_schema: {
      dimensions: ["final_score"],
      summary_fields: [
        { key: "runtime_profile_id", value_type: "string" },
        { key: "rdkit_version", value_type: "string" },
        { key: "xgboost_version", value_type: "string" },
        { key: "pandas_version", value_type: "string" },
        { key: "scipy_version", value_type: "string" },
        { key: "joblib_version", value_type: "string" },
        { key: "opensol_model_sha256", value_type: "string" },
        { key: "opensol_ethanol_log_s", value_type: "number" },
        { key: "ethanol_canonical_smiles", value_type: "string" },
        { key: "ethanol_heavy_atoms", value_type: "number" },
        { key: "ethanol_mol_wt", value_type: "number" },
        { key: "benzene_morgan_bits", value_type: "number" },
        { key: "contains_hydroxyl", value_type: "boolean" },
      ],
      allow_additional_details: false,
    },
    policies: {
      coverage_policy: "reject",
      duplicate_id_policy: "reject",
      invalid_value_policy: "reject",
    },
  };

  await fs.writeFile(
    path.join(inputDir, "runtime-manifest.json"),
    JSON.stringify(runtimeManifest),
  );
  return { inputDir, outputPath };
}

function assertSmokeOutput(payload) {
  const expectedDetails = {
    runtime_profile_id: "rdkit_python_runtime",
    rdkit_version: "2025.03.1",
    xgboost_version: "3.0.5",
    pandas_version: "2.3.3",
    scipy_version: "1.17.1",
    joblib_version: "1.5.3",
    opensol_model_sha256:
      "bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0",
    ethanol_canonical_smiles: "CCO",
    ethanol_heavy_atoms: 3,
    ethanol_mol_wt: 46.069,
    benzene_morgan_bits: 3,
    contains_hydroxyl: true,
  };
  if (payload.ok !== true || payload.score !== 1) {
    throw new Error(`Unexpected RDKit smoke score envelope: ${JSON.stringify(payload)}`);
  }
  for (const [key, expected] of Object.entries(expectedDetails)) {
    if (payload.details?.[key] !== expected) {
      throw new Error(
        `Unexpected RDKit smoke detail ${key}: expected ${JSON.stringify(
          expected,
        )}, found ${JSON.stringify(payload.details?.[key])}.`,
      );
    }
  }
  const logS = payload.details?.opensol_ethanol_log_s;
  if (typeof logS !== "number" || !Number.isFinite(logS)) {
    throw new Error(
      `Unexpected OpenSOL smoke logS detail: found ${JSON.stringify(logS)}.`,
    );
  }
}

async function main() {
  if (!requestedImage) {
    await checkedRun(
      "docker",
      ["build", "-t", image, "-f", "agora-scorer-rdkit/Dockerfile", "."],
      { cwd: rootDir },
    );
  }

  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "agora-rdkit-smoke-"));
  try {
    const { inputDir, outputPath } = await stageSmokeWorkspace(workspace, image);
    const run = await checkedRun("docker", [
      "run",
      "--rm",
      "--network=none",
      "--read-only",
      "--cap-drop=ALL",
      "--security-opt=no-new-privileges",
      "--user",
      "65532:65532",
      "--memory",
      "2g",
      "--cpus",
      "2",
      "--pids-limit",
      "64",
      "--tmpfs",
      "/tmp:size=64m",
      "--tmpfs",
      "/output:size=4194304,uid=65532,gid=65532,mode=700",
      "--mount",
      `type=bind,src=${inputDir},dst=/input,readonly`,
      "--mount",
      `type=bind,src=${outputPath},dst=/output/score.json`,
      image,
    ]);
    if (run.stderr.trim()) {
      process.stderr.write(`${run.stderr.trim()}\n`);
    }
    const payload = JSON.parse(await fs.readFile(outputPath, "utf8"));
    assertSmokeOutput(payload);
    console.log(
      "rdkit image smoke passed: rdkit_python_runtime imported RDKit 2025.03.1 and executed pinned OpenSOL XGBoost/RDKit-2D prediction",
    );
  } finally {
    await fs.rm(workspace, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
