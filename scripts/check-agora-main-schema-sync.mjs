import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const ARTIFACTS = [
  {
    label: "runtime manifest",
    key: "runtime_manifest",
    localSchemaPath: path.join(
      REPO_ROOT,
      "schema/scorer-runtime-manifest.canonical.schema.json",
    ),
    localSha256Path: path.join(
      REPO_ROOT,
      "schema/scorer-runtime-manifest.canonical.sha256",
    ),
    sidecarFileName: "scorer-runtime-manifest.canonical.schema.json",
    envPath: "AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_PATH",
    envUrl: "AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_URL",
    defaultUrl:
      "https://raw.githubusercontent.com/moleculeprotocol/Agora/main/packages/common/src/schemas/scorer-runtime-manifest.canonical.schema.json",
  },
  {
    label: "proof bundle",
    key: "proof_bundle",
    localSchemaPath: path.join(
      REPO_ROOT,
      "schema/proof-bundle.canonical.schema.json",
    ),
    localSha256Path: path.join(
      REPO_ROOT,
      "schema/proof-bundle.canonical.sha256",
    ),
    sidecarFileName: "proof-bundle.canonical.schema.json",
    envPath: "AGORA_MAIN_PROOF_BUNDLE_SCHEMA_PATH",
    envUrl: "AGORA_MAIN_PROOF_BUNDLE_SCHEMA_URL",
    defaultUrl:
      "https://raw.githubusercontent.com/moleculeprotocol/Agora/main/packages/common/src/schemas/proof-bundle.canonical.schema.json",
  },
];

function computeSha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function readSha256Sidecar(filePath, artifact) {
  const contents = fs.readFileSync(filePath, "utf8").trim();
  const match = /^([0-9a-f]{64})\s+\S+\s*$/.exec(contents);
  if (!match) {
    throw new Error(
      `Invalid ${artifact.label} schema sha256 sidecar at ${filePath}. Next step: write "<sha256>  ${artifact.sidecarFileName}" and retry.`,
    );
  }
  return match[1];
}

async function readAgoraMainSchemaBytes(artifact, env, fetchImpl) {
  const localAgoraSchemaPath = env[artifact.envPath]?.trim();
  if (localAgoraSchemaPath) {
    return fs.readFileSync(localAgoraSchemaPath);
  }

  const agoraSchemaUrl = env[artifact.envUrl]?.trim() || artifact.defaultUrl;
  const githubToken =
    env.AGORA_MAIN_GITHUB_TOKEN?.trim() || env.GITHUB_TOKEN?.trim();
  const response = await fetchImpl(agoraSchemaUrl, {
    headers: githubToken ? { Authorization: `Bearer ${githubToken}` } : {},
  });
  if (!response.ok) {
    throw new Error(
      `Failed to fetch Agora main ${artifact.label} schema from ${agoraSchemaUrl} (${response.status}). Next step: set ${artifact.envPath} to a local Agora checkout artifact or set AGORA_MAIN_GITHUB_TOKEN/GITHUB_TOKEN with read access to moleculeprotocol/Agora and retry.`,
    );
  }

  return Buffer.from(await response.arrayBuffer());
}

export async function verifyAgoraMainSchemaSync(
  env = process.env,
  fetchImpl = fetch,
) {
  const results = [];

  for (const artifact of ARTIFACTS) {
    if (!fs.existsSync(artifact.localSchemaPath)) {
      throw new Error(
        `Missing vendored ${artifact.label} schema at ${artifact.localSchemaPath}. Next step: revendor the Agora main canonical schema artifact and retry.`,
      );
    }
    if (!fs.existsSync(artifact.localSha256Path)) {
      throw new Error(
        `Missing ${artifact.label} schema sha256 sidecar at ${artifact.localSha256Path}. Next step: update the schema sha256 sidecar and retry.`,
      );
    }

    const agoraBytes = await readAgoraMainSchemaBytes(
      artifact,
      env,
      fetchImpl,
    );
    const localBytes = fs.readFileSync(artifact.localSchemaPath);
    const agoraSha256 = computeSha256Hex(agoraBytes);
    const localSha256 = computeSha256Hex(localBytes);
    const sidecarSha256 = readSha256Sidecar(
      artifact.localSha256Path,
      artifact,
    );

    if (!agoraBytes.equals(localBytes)) {
      throw new Error(
        `Vendored ${artifact.label} schema drift from Agora main: agora_main_sha256=${agoraSha256}, local_sha256=${localSha256}. Next step: revendor the Agora main canonical ${artifact.label} schema into ${path.relative(REPO_ROOT, artifact.localSchemaPath)} and update ${path.relative(REPO_ROOT, artifact.localSha256Path)}.`,
      );
    }

    if (sidecarSha256 !== localSha256) {
      throw new Error(
        `Local ${artifact.label} schema sha256 sidecar mismatch: sidecar=${sidecarSha256}, expected=${localSha256}. Next step: update ${path.relative(REPO_ROOT, artifact.localSha256Path)} and retry.`,
      );
    }

    results.push({
      label: artifact.label,
      key: artifact.key,
      agoraSha256,
      source:
        env[artifact.envPath]?.trim() ||
        env[artifact.envUrl]?.trim() ||
        artifact.defaultUrl,
    });
  }

  return results;
}

export async function main(env = process.env, fetchImpl = fetch) {
  const results = await verifyAgoraMainSchemaSync(env, fetchImpl);
  console.log(
    `[agora-main-schema-sync] in sync ${results
      .map((result) => `${result.key}_sha256=${result.agoraSha256}`)
      .join(" ")} sources=${results.map((result) => result.source).join(",")}`,
  );
}

if (
  process.argv[1] &&
  fileURLToPath(import.meta.url) === path.resolve(process.argv[1])
) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
