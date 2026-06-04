import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const rootDir = process.cwd();
const defaultImage = "agora-scorer-compiled-smoke:local";
const requestedImage = process.env.AGORA_COMPILED_RUNTIME_IMAGE?.trim();
const image = requestedImage || defaultImage;

function buildEnvironment() {
  const environment = { ...process.env };
  const requestedBuildkit = process.env.AGORA_COMPILED_SMOKE_DOCKER_BUILDKIT;
  if (requestedBuildkit !== undefined) {
    environment.DOCKER_BUILDKIT = requestedBuildkit;
    return environment;
  }
  if (process.platform === "darwin") {
    environment.DOCKER_BUILDKIT = "0";
  }
  return environment;
}

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

from runtime_manifest import (
    load_runtime_manifest,
    resolve_artifact_by_role,
    resolve_scoring_asset_by_role,
)


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


def resolve_scoring_asset(runtime_context, role, *, kind=None):
    return resolve_scoring_asset_by_role(
        runtime_context,
        role=role,
        kind=kind,
        fail_runtime=fail_runtime,
    )["path"]


def load_json_file(path, *, label="JSON file"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail_runtime(f"{label} is not valid JSON: {exc}")
`.trim();
}

function toxinpred3ProgramSource() {
  return String.raw`
import csv
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from agora_runtime import (
    fail_runtime,
    load_json_file,
    load_runtime_context,
    resolve_scoring_asset,
    resolve_submission_artifact,
    write_score,
)


def parse_single_fasta(path):
    lines = [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) < 2 or not lines[0].startswith(">"):
        fail_runtime("Candidate FASTA must contain one record.")
    if any(line.startswith(">") for line in lines[1:]):
        fail_runtime("Candidate FASTA must contain exactly one record.")
    return {
        "id": lines[0][1:].split()[0],
        "sequence": "".join(lines[1:]).upper(),
    }


def parse_toxinpred3_csv(output_csv, candidate_id):
    with Path(output_csv).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get("Subject") == candidate_id:
            return row
    fail_runtime("ToxinPred3 output CSV did not include the candidate row.")


def main():
    runtime_context = load_runtime_context()
    config = load_json_file(
        resolve_scoring_asset(runtime_context, "compiled_config", kind="config"),
        label="compiled_config",
    )
    threshold = float(config["threshold"])
    model = int(config["model"])
    record = parse_single_fasta(
        resolve_submission_artifact(runtime_context, config["submission_role"])
    )
    executable = shutil.which("toxinpred3")
    if executable is None:
        fail_runtime("ToxinPred3 executable is not available.")

    with tempfile.TemporaryDirectory(prefix="agora-toxinpred3-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        cli_input = temp_root / "candidate-with-sentinel.fasta"
        cli_output = temp_root / "toxinpred3-output.csv"
        cli_input.write_text(
            "\n".join(
                [
                    f">{record['id']}",
                    record["sequence"],
                    ">agora_batch_shape_sentinel",
                    "ACDEFGHIKLMNPQRSTVWY",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                executable,
                "-i",
                str(cli_input),
                "-o",
                str(cli_output),
                "-t",
                format(threshold, ".17g"),
                "-m",
                str(model),
                "-d",
                "2",
            ],
            cwd=temp_root,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            fail_runtime(
                "ToxinPred3 execution failed.",
                details={
                    "stdout": completed.stdout[-1000:],
                    "stderr": completed.stderr[-1000:],
                    "returncode": completed.returncode,
                },
            )
        row = parse_toxinpred3_csv(cli_output, record["id"])

    toxicity_score = float(row["Hybrid Score"])
    if not math.isfinite(toxicity_score) or toxicity_score < 0 or toxicity_score > 1:
        fail_runtime("ToxinPred3 Hybrid Score must be finite and bounded.")
    prediction = "toxic" if toxicity_score > threshold else "non_toxic"
    raw_prediction = row["Prediction"]
    if raw_prediction not in {"Toxin", "Non-Toxin"}:
        fail_runtime("ToxinPred3 Prediction must be Toxin or Non-Toxin.")
    if (raw_prediction == "Toxin") != (prediction == "toxic"):
        fail_runtime("ToxinPred3 Prediction does not match Hybrid Score and threshold.")

    pass_score = 0.0 if prediction == "toxic" else 1.0
    write_score(
        score=pass_score,
        details={
            "score": pass_score,
            "toxicity_score": toxicity_score,
            "prediction": prediction,
            "threshold": threshold,
            "threshold_comparator": ">",
            "model": model,
            "model_label": "hybrid",
            "package_name": config["package_name"],
            "package_version": config["package_version"],
            "package_source": "pypi",
            "toxicity_score_key": "Hybrid Score",
            "raw_prediction": raw_prediction,
            "runtime_profile_id": runtime_context["runtime_profile"]["profile_id"],
            "sequence_id": record["id"],
            "sequence_length": len(record["sequence"]),
            "single_sequence_batch_workaround": "sentinel_record",
        },
    )


if __name__ == "__main__":
    main()
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

  const candidateStats = await writePayload(
    path.join(inputDir, "submission", "candidate", "candidate.fasta"),
    ">candidate\nGIGKFLHSAKKFGKAFVGEIMNS\n",
  );
  const configStats = await writePayload(
    path.join(inputDir, "scoring_assets", "compiled_config", "score-config.json"),
    JSON.stringify({
      threshold: 0.38,
      model: 2,
      package_name: "toxinpred3",
      package_version: "1.4",
      submission_role: "candidate",
    }),
  );
  const programStats = await writePayload(
    path.join(inputDir, "scoring_assets", "compiled_program", "score.py"),
    toxinpred3ProgramSource(),
  );
  const sdkStats = await writePayload(
    path.join(inputDir, "scoring_assets", "python_v1_runtime_sdk", "agora_runtime.py"),
    sdkSource(),
  );

  const artifactContract = {
    evaluation: [],
    submission: [
      {
        role: "candidate",
        required: true,
        description: "Candidate peptide FASTA",
        file: {
          extension: ".fasta",
          mime_type: "text/x-fasta",
          max_bytes: 4096,
        },
        validator: {
          kind: "protein_sequence_fasta",
          max_length: 2048,
          alphabet: "protein",
          require_single_record: true,
          allow_ambiguous: false,
        },
      },
    ],
    relations: [],
  };
  const runtimeManifest = {
    kind: "runtime_manifest",
    runtime_profile: {
      kind: "official",
      profile_id: "official_compiled_runtime",
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
        role: "candidate",
        required: true,
        present: true,
        validator: artifactContract.submission[0].validator,
        relative_path: "submission/candidate/candidate.fasta",
        file_name: "candidate.fasta",
        mime_type: "text/x-fasta",
        ...candidateStats,
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
        role: "compiled_config",
        kind: "config",
        artifact_id: "score-config.json",
        relative_path: "scoring_assets/compiled_config/score-config.json",
        file_name: "score-config.json",
        ...configStats,
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
    final_score_key: "score",
    scorer_result_schema: {
      dimensions: ["score", "toxicity_score"],
      summary_fields: [
        { key: "prediction", value_type: "string" },
        { key: "threshold", value_type: "number" },
        { key: "threshold_comparator", value_type: "string" },
        { key: "model", value_type: "number" },
        { key: "model_label", value_type: "string" },
        { key: "package_name", value_type: "string" },
        { key: "package_version", value_type: "string" },
        { key: "runtime_profile_id", value_type: "string" },
      ],
      allow_additional_details: true,
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
    score: 0,
    toxicity_score: 0.5,
    prediction: "toxic",
    threshold: 0.38,
    threshold_comparator: ">",
    model: 2,
    model_label: "hybrid",
    package_name: "toxinpred3",
    package_version: "1.4",
    package_source: "pypi",
    toxicity_score_key: "Hybrid Score",
    raw_prediction: "Toxin",
    runtime_profile_id: "official_compiled_runtime",
    sequence_id: "candidate",
    sequence_length: 23,
    single_sequence_batch_workaround: "sentinel_record",
  };
  if (payload.ok !== true || payload.score !== 0) {
    throw new Error(`Unexpected compiled smoke score envelope: ${JSON.stringify(payload)}`);
  }
  for (const [key, expected] of Object.entries(expectedDetails)) {
    if (payload.details?.[key] !== expected) {
      throw new Error(
        `Unexpected compiled smoke detail ${key}: expected ${JSON.stringify(
          expected,
        )}, found ${JSON.stringify(payload.details?.[key])}.`,
      );
    }
  }
}

async function main() {
  if (!requestedImage) {
    await checkedRun(
      "docker",
      ["build", "-t", image, "-f", "agora-scorer-compiled/Dockerfile", "."],
      {
        cwd: rootDir,
        env: buildEnvironment(),
      },
    );
  }

  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "agora-compiled-smoke-"));
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
      "/tmp:size=256m",
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
      "compiled image smoke passed: official_compiled_runtime executed toxinpred3==1.4 model 2 and produced deterministic toxicity details",
    );
  } finally {
    await fs.rm(workspace, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
