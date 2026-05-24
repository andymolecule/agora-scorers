import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const LOCAL_SCHEMA_PATH = path.join(
  REPO_ROOT,
  "schema/scorer-runtime-manifest.canonical.schema.json",
);
const LOCAL_SHA256_PATH = path.join(
  REPO_ROOT,
  "schema/scorer-runtime-manifest.canonical.sha256",
);
const DEFAULT_AGORA_SCHEMA_URL =
  "https://raw.githubusercontent.com/moleculeprotocol/Agora/main/packages/common/src/schemas/scorer-runtime-manifest.canonical.schema.json";

function computeSha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function readSha256Sidecar(filePath) {
  const contents = fs.readFileSync(filePath, "utf8").trim();
  const match = /^([0-9a-f]{64})\s+\S+\s*$/.exec(contents);
  if (!match) {
    throw new Error(
      `Invalid runtime manifest schema sha256 sidecar at ${filePath}. Next step: write "<sha256>  scorer-runtime-manifest.canonical.schema.json" and retry.`,
    );
  }
  return match[1];
}

async function readAgoraMainSchemaBytes(env, fetchImpl) {
  const localAgoraSchemaPath = env.AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_PATH?.trim();
  if (localAgoraSchemaPath) {
    return fs.readFileSync(localAgoraSchemaPath);
  }

  const agoraSchemaUrl =
    env.AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_URL?.trim() ||
    DEFAULT_AGORA_SCHEMA_URL;
  const githubToken =
    env.AGORA_MAIN_GITHUB_TOKEN?.trim() || env.GITHUB_TOKEN?.trim();
  const response = await fetchImpl(agoraSchemaUrl, {
    headers: githubToken ? { Authorization: `Bearer ${githubToken}` } : {},
  });
  if (!response.ok) {
    throw new Error(
      `Failed to fetch Agora main runtime manifest schema from ${agoraSchemaUrl} (${response.status}). Next step: set AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_PATH to a local Agora checkout artifact or set AGORA_MAIN_GITHUB_TOKEN/GITHUB_TOKEN with read access to moleculeprotocol/Agora and retry.`,
    );
  }

  return Buffer.from(await response.arrayBuffer());
}

export async function verifyAgoraMainSchemaSync(
  env = process.env,
  fetchImpl = fetch,
) {
  if (!fs.existsSync(LOCAL_SCHEMA_PATH)) {
    throw new Error(
      `Missing vendored schema at ${LOCAL_SCHEMA_PATH}. Next step: revendor the Agora main canonical schema artifact and retry.`,
    );
  }
  if (!fs.existsSync(LOCAL_SHA256_PATH)) {
    throw new Error(
      `Missing schema sha256 sidecar at ${LOCAL_SHA256_PATH}. Next step: update schema/scorer-runtime-manifest.canonical.sha256 and retry.`,
    );
  }

  const agoraBytes = await readAgoraMainSchemaBytes(env, fetchImpl);
  const localBytes = fs.readFileSync(LOCAL_SCHEMA_PATH);
  const agoraSha256 = computeSha256Hex(agoraBytes);
  const localSha256 = computeSha256Hex(localBytes);
  const sidecarSha256 = readSha256Sidecar(LOCAL_SHA256_PATH);

  if (!agoraBytes.equals(localBytes)) {
    throw new Error(
      `Vendored runtime manifest schema drift from Agora main: agora_main_sha256=${agoraSha256}, local_sha256=${localSha256}. Next step: revendor packages/common/src/schemas/scorer-runtime-manifest.canonical.schema.json from moleculeprotocol/Agora main into schema/scorer-runtime-manifest.canonical.schema.json and update schema/scorer-runtime-manifest.canonical.sha256.`,
    );
  }

  if (sidecarSha256 !== localSha256) {
    throw new Error(
      `Local schema sha256 sidecar mismatch: sidecar=${sidecarSha256}, expected=${localSha256}. Next step: update schema/scorer-runtime-manifest.canonical.sha256 and retry.`,
    );
  }

  return {
    agoraSha256,
    source:
      env.AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_PATH?.trim() ||
      env.AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_URL?.trim() ||
      DEFAULT_AGORA_SCHEMA_URL,
  };
}

export async function main(env = process.env, fetchImpl = fetch) {
  const result = await verifyAgoraMainSchemaSync(env, fetchImpl);
  console.log(
    `[agora-main-schema-sync] in sync sha256=${result.agoraSha256} source=${result.source}`,
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
