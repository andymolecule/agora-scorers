import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import yaml from "yaml";
import { SUPPORTED_PROGRAM_ABI_VERSIONS } from "../src/constants.js";
import { challengeSpecSchema, proofBundleSchema } from "../src/contracts.js";
import { computeDeterminismEnvSha256, replayProof } from "../src/replay.js";
import {
  readProofBundleSchemaSha256,
  readRuntimeManifestSchemaSha256,
} from "../src/schema-hash.js";
import { sha256Hex } from "../src/hash.js";
import { stageReplayWorkspace } from "../src/stage.js";
import { createStoredZipArchive } from "../src/stored-zip.js";

const IMAGE =
  "ghcr.io/moleculeprotocol/agora-scorer-compiled@sha256:1111111111111111111111111111111111111111111111111111111111111111";
const DETERMINISM_ENV = {
  LANG: "C.UTF-8",
  LC_ALL: "C.UTF-8",
  PYTHONHASHSEED: "0",
  SOURCE_DATE_EPOCH: "0",
  TZ: "UTC",
};
const SCORE_PROOF_FACTS = {
  kind: "score_proof_facts",
  scoring_profile_id: "official_compiled_runtime",
  score_basis_commitment:
    "0xe37730d617634fbb6b380ea1d7d94e3cdbf7fa04e4e8cf9748ed64a171299929",
  runtime_manifest_digest:
    "2222222222222222222222222222222222222222222222222222222222222222",
  private_input_commitment:
    "0x4bf406c6aa679448dc09fe15365b166e8c9e6c1cee919e9fb0900c848bd46a89",
  artifact_digest_policy: "private_no_public_equality_digest",
};

const encoder = new TextEncoder();
const tests = [];

function test(name, fn) {
  tests.push({ name, fn });
}

function bytes(value) {
  return encoder.encode(value);
}

async function createTempDir() {
  return await fs.mkdtemp(path.join(os.tmpdir(), "agora-replay-test-"));
}

async function withCwd(cwd, callback) {
  const previousCwd = process.cwd();
  process.chdir(cwd);
  try {
    return await callback();
  } finally {
    process.chdir(previousCwd);
  }
}

function buildSpec(overrides = {}) {
  const evalBytes = bytes("id,target\n1,0.9\n");
  const programBytes = bytes('print("program")\n');
  const sdkBytes = bytes("# python-v1 sdk\n");
  const configBytes = bytes('{"mode":"fixture"}\n');
  const programAbiVersion = overrides.programAbiVersion ?? "python-v1";
  const runtimeSupported =
    overrides.runtimeSupported ?? SUPPORTED_PROGRAM_ABI_VERSIONS;

  const spec = {
    schema_version: 5,
    id: "fixture-challenge",
    execution: {
      runtime_profile: {
        kind: "official",
        profile_id: "official_compiled_runtime",
        image: IMAGE,
        limits: {
          memory: "256m",
          cpus: "1",
          pids: 64,
          timeoutMs: 30000,
        },
        supported_program_abi_versions: runtimeSupported,
        determinism_env: DETERMINISM_ENV,
      },
      artifact_contract: {
        evaluation: [
          {
            role: "gold",
            required: true,
            description: "Public gold fixture.",
            file: {
              extension: ".csv",
              max_bytes: 1024,
              mime_type: "text/csv",
            },
            validator: { kind: "none" },
          },
        ],
        submission: [
          {
            role: "answer",
            required: true,
            description: "Solver answer fixture.",
            file: {
              extension: ".csv",
              max_bytes: 1024,
              mime_type: "text/csv",
            },
            validator: { kind: "none" },
          },
        ],
        relations: [],
      },
      evaluation_bindings: [
        {
          kind: "artifact",
          role: "gold",
          artifact_id: "gold_fixture",
        },
      ],
      scoring_asset_sources: [
        {
          role: "compiled_program",
          kind: "program",
          artifact_id: "program_fixture",
          abi_version: programAbiVersion,
          entrypoint: "score.py",
          uri: "ipfs://programcid",
          file_name: "score.py",
          size_bytes: programBytes.byteLength,
          sha256: sha256Hex(programBytes),
        },
        {
          role: "python_v1_runtime_sdk",
          kind: "document",
          artifact_id: "sdk_fixture",
          uri: "ipfs://sdkcid",
          file_name: "agora_runtime.py",
          size_bytes: sdkBytes.byteLength,
          sha256: sha256Hex(sdkBytes),
        },
        {
          role: "scoring_config",
          kind: "config",
          artifact_id: "config_fixture",
          uri: "ipfs://configcid",
          file_name: "config.json",
          size_bytes: configBytes.byteLength,
          sha256: sha256Hex(configBytes),
        },
      ],
      objective: "maximize",
      final_score_key: "final_score",
      scorer_result_schema: {
        dimensions: [{ key: "final_score", value_type: "number" }],
        bonuses: [],
        penalties: [],
        summary_fields: [],
        allow_additional_details: true,
      },
      policies: {
        coverage_policy: "ignore",
        duplicate_id_policy: "ignore",
        invalid_value_policy: "ignore",
      },
    },
    artifacts: [
      {
        artifact_id: "gold_fixture",
        role: "gold",
        visibility: "public",
        uri: "ipfs://evalcid",
        file_name: "gold.csv",
        mime_type: "text/csv",
        size_bytes: evalBytes.byteLength,
        sha256: sha256Hex(evalBytes),
      },
    ],
  };

  return {
    spec,
    files: {
      evalcid: evalBytes,
      programcid: programBytes,
      sdkcid: sdkBytes,
      configcid: configBytes,
    },
  };
}

function buildProofFixture(overrides = {}) {
  return {
    score: overrides.score ?? 0.9,
    container_image_digest: overrides.containerImageDigest ?? IMAGE,
    challenge_spec_cid: overrides.challengeSpecCid ?? "ipfs://speccid",
    score_proof_facts: overrides.scoreProofFacts ?? SCORE_PROOF_FACTS,
    meta: {
      challenge_id: "fixture-challenge",
      submission_id: "fixture-submission",
    },
  };
}

async function withFetchFixture(routes, callback) {
  const previousFetch = globalThis.fetch;
  const gateway = "https://fixture.local";
  globalThis.fetch = async (url) => {
    const parsed = new URL(String(url));
    const key = parsed.pathname.replace(/^\/ipfs\//, "");
    const body = routes[key];
    if (!body) {
      return new Response("missing fixture", { status: 404 });
    }
    return new Response(body, { status: 200 });
  };
  try {
    return await callback(gateway);
  } finally {
    globalThis.fetch = previousFetch;
  }
}

async function runFixture(options = {}) {
  const proof = buildProofFixture(options);
  return await withFetchFixture(
    { proofcid: Buffer.from(JSON.stringify(proof)) },
    async (gateway) =>
      await replayProof({
        proof: "proofcid",
        ipfsGateway: gateway,
        format: "json",
        keepWorkspace: false,
        expectedProofHash: options.expectedProofHash,
      }),
  );
}

test("accepts Agora-shaped schema v5 runtime profile limits and determinism env", () => {
  const { spec } = buildSpec();
  const parsed = challengeSpecSchema.parse(spec);
  assert.equal(parsed.execution.runtime_profile.limits.timeoutMs, 30000);
  assert.deepEqual(
    parsed.execution.runtime_profile.determinism_env,
    DETERMINISM_ENV,
  );
});

test("rejects runtime profiles without determinism env", () => {
  const { spec } = buildSpec();
  delete spec.execution.runtime_profile.determinism_env;
  assert.throws(() => challengeSpecSchema.parse(spec), /determinism_env/i);
});

test("rejects evaluation bindings without artifact ids", () => {
  const { spec } = buildSpec();
  delete spec.execution.evaluation_bindings[0].artifact_id;
  assert.throws(() => challengeSpecSchema.parse(spec), /artifact_id/i);
});

test("accepts the optimistic-private proof bundle shape", () => {
  const parsed = proofBundleSchema.parse(buildProofFixture());
  assert.equal(parsed.score, 0.9);
  assert.equal(parsed.challenge_spec_cid, "ipfs://speccid");
  assert.deepEqual(parsed.score_proof_facts, SCORE_PROOF_FACTS);
});

test("rejects retired public replay proof fields", () => {
  const retiredFields = {
    input_hash: "a".repeat(64),
    output_hash: "b".repeat(64),
    replay_submission_cid: "replaycid",
    timelocked_submission: {},
    timelocked_private_artifacts: [],
  };

  for (const [field, value] of Object.entries(retiredFields)) {
    assert.throws(
      () => proofBundleSchema.parse({ ...buildProofFixture(), [field]: value }),
      new RegExp(field),
    );
  }
});

test("rejects proof bundles without score_proof_facts", () => {
  const proof = buildProofFixture();
  delete proof.score_proof_facts;
  assert.throws(() => proofBundleSchema.parse(proof), /score_proof_facts/);
});

test("rejects camelCase proof bundle fields", () => {
  const camelCaseProof = {
    score: 0.9,
    containerImageDigest: IMAGE,
    challengeSpecCid: "speccid",
    scoreProofFacts: SCORE_PROOF_FACTS,
    meta: {
      challengeId: "fixture-challenge",
      submissionId: "fixture-submission",
    },
  };
  assert.throws(
    () => proofBundleSchema.parse(camelCaseProof),
    /score_proof_facts|containerImageDigest/,
  );
});

test("admits private score proofs and reports the public replay boundary", async () => {
  const result = await runFixture();
  assert.equal(result.status, "not_publicly_replayable");
  assert.equal(result.reason, "private_answer_not_publicly_replayable");
  assert.equal(result.replay_available, false);
  assert.equal(result.replay_scope, "challenge_reveal_only");
  assert.equal(result.score, 0.9);
  assert.equal(result.challenge_spec_cid, "ipfs://speccid");
  assert.equal(result.runtime_profile_id, "official_compiled_runtime");
  assert.equal(result.image_digest, IMAGE);
  assert.deepEqual(result.score_proof_facts, SCORE_PROOF_FACTS);
  assert.match(result.runtime_manifest_schema_sha256, /^[a-f0-9]{64}$/);
  assert.match(result.proof_bundle_schema_sha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(result.supported_program_abi_versions, ["python-v1"]);
  assert.deepEqual(result.mismatches, []);
});

test("admits private score proofs from an arbitrary user working directory", async () => {
  const userCwd = await createTempDir();
  try {
    const result = await withCwd(userCwd, async () => await runFixture());
    assert.equal(result.status, "not_publicly_replayable");
    assert.match(result.runtime_manifest_schema_sha256, /^[a-f0-9]{64}$/);
  } finally {
    await fs.rm(userCwd, { recursive: true, force: true });
  }
});

test("reports proof hash mismatches without attempting public replay", async () => {
  const expectedProofHash =
    "0x0000000000000000000000000000000000000000000000000000000000000000";
  const result = await runFixture({ expectedProofHash });
  assert.equal(result.status, "mismatched");
  assert.equal(result.reason, "proof_hash_mismatch");
  assert.deepEqual(result.mismatches, [
    {
      field: "proof_hash",
      expected: expectedProofHash,
      actual: result.proof_hash,
    },
  ]);
});

test("admits the checked-in challenge 7 private proof bundle fixture", async () => {
  const proof = JSON.parse(
    await fs.readFile("test/fixtures/challenge-7-proof-bundle.json", "utf8"),
  );
  const parsed = proofBundleSchema.parse(proof);
  assert.equal(parsed.score, 0.3712485568109655);
  assert.equal(
    parsed.challenge_spec_cid,
    "ipfs://bafkreig6xq3nsvmf2qoj7witf2jnhvhn7bj7m7hcwqzgwczxsskwlss3we",
  );
  assert.equal(parsed.score_proof_facts.kind, "score_proof_facts");
  assert.equal(parsed.meta.challenge_id, "7");
  assert.equal(
    parsed.meta.submission_id,
    "bc52fe65-5246-4aa4-8aa3-00e4dfe76ed4",
  );
});

test("admits the real challenge 7 emitted challenge spec", async () => {
  const spec = JSON.parse(
    await fs.readFile("test/fixtures/challenge-7-spec.json", "utf8"),
  );
  const parsed = challengeSpecSchema.parse(spec);
  assert.equal(parsed.schema_version, 6);
  assert.equal(parsed.execution.scoring_assets.length, 8);
  assert.equal(
    parsed.execution.runtime_profile.profile_id,
    "official_compiled_runtime",
  );
});

test("stages schema v6 private replay artifacts for evaluation and scoring assets", async () => {
  const { spec, files } = buildSpec();
  const scoringAssetSources = spec.execution.scoring_asset_sources;
  spec.schema_version = 6;
  spec.artifacts[0].visibility = "private";
  delete spec.artifacts[0].uri;
  spec.execution.scoring_assets = scoringAssetSources.map((source) => ({
    role: source.role,
    kind: source.kind,
    artifact_id: source.artifact_id,
    ...(source.abi_version ? { abi_version: source.abi_version } : {}),
    ...(source.entrypoint ? { entrypoint: source.entrypoint } : {}),
    ...(source.file_name ? { file_name: source.file_name } : {}),
    ...(source.mime_type ? { mime_type: source.mime_type } : {}),
  }));
  spec.execution.scoring_asset_sources = [];

  const replayBundle = createStoredZipArchive([
    {
      relativePath: "submission/answer/answer.csv",
      bytes: bytes("id,prediction\n1,0.9\n"),
    },
  ]);
  const privateReplayArtifacts = [
    {
      lane: "evaluation",
      role: "gold",
      artifact_id: "gold_fixture",
      replay_artifact_uri: "ipfs://evalcid",
      staged_relative_path: "evaluation/gold/gold.csv",
      size_bytes: files.evalcid.byteLength,
      sha256: sha256Hex(files.evalcid),
    },
    ...scoringAssetSources.map((source) => {
      const cid = source.uri.replace("ipfs://", "");
      const content = files[cid];
      return {
        lane: "scoring_asset",
        role: source.role,
        artifact_id: source.artifact_id,
        replay_artifact_uri: source.uri,
        staged_relative_path: `scoring_assets/${source.role}/${source.file_name}`,
        size_bytes: content.byteLength,
        sha256: sha256Hex(content),
      };
    }),
  ];
  const tempDir = await createTempDir();
  try {
    await withFetchFixture(
      Object.fromEntries(
        Object.entries(files).map(([cid, content]) => [
          cid,
          Buffer.from(content),
        ]),
      ),
      async (gateway) => {
        const inputDir = path.join(tempDir, "input");
        await fs.mkdir(inputDir, { recursive: true });
        const staged = await stageReplayWorkspace({
          spec: challengeSpecSchema.parse(spec),
          image: IMAGE,
          inputDir,
          replayBundleBytes: replayBundle,
          gateway,
          privateReplayArtifacts,
        });
        assert.deepEqual(
          staged.programAssets.map((asset) => asset.role),
          ["compiled_program"],
        );
        assert.equal(
          staged.inputPaths.some((inputPath) =>
            inputPath.endsWith("scoring_assets/compiled_program/score.py"),
          ),
          true,
        );
      },
    );
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
  }
});

test("computes deterministic environment hashes with stable key ordering", () => {
  assert.equal(
    computeDeterminismEnvSha256({ TZ: "UTC", LANG: "C.UTF-8" }),
    computeDeterminismEnvSha256({ LANG: "C.UTF-8", TZ: "UTC" }),
  );
});

test("rejects stale vendored runtime schema hashes", async () => {
  const rootDir = await createTempDir();
  try {
    await fs.mkdir(path.join(rootDir, "schema"), { recursive: true });
    await fs.writeFile(
      path.join(rootDir, "schema/scorer-runtime-manifest.canonical.schema.json"),
      "{}",
    );
    await fs.writeFile(
      path.join(rootDir, "schema/scorer-runtime-manifest.canonical.sha256"),
      "0000000000000000000000000000000000000000000000000000000000000000  scorer-runtime-manifest.canonical.schema.json\n",
    );
    await assert.rejects(
      readRuntimeManifestSchemaSha256(rootDir),
      /schema hash does not match/,
    );
  } finally {
    await fs.rm(rootDir, { recursive: true, force: true });
  }
});

test("rejects stale vendored proof bundle schema hashes", async () => {
  const rootDir = await createTempDir();
  try {
    await fs.mkdir(path.join(rootDir, "schema"), { recursive: true });
    await fs.writeFile(
      path.join(rootDir, "schema/proof-bundle.canonical.schema.json"),
      "{}",
    );
    await fs.writeFile(
      path.join(rootDir, "schema/proof-bundle.canonical.sha256"),
      "0000000000000000000000000000000000000000000000000000000000000000  proof-bundle.canonical.schema.json\n",
    );
    await assert.rejects(
      readProofBundleSchemaSha256(rootDir),
      /schema hash does not match/,
    );
  } finally {
    await fs.rm(rootDir, { recursive: true, force: true });
  }
});

let failures = 0;
for (const { name, fn } of tests) {
  try {
    await fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`not ok - ${name}`);
    console.error(error);
  }
}

if (failures > 0) {
  process.exitCode = 1;
}
