import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  PROOF_BUNDLE_SCHEMA_HASH_PATH,
  PROOF_BUNDLE_SCHEMA_PATH,
  RUNTIME_MANIFEST_SCHEMA_HASH_PATH,
  RUNTIME_MANIFEST_SCHEMA_PATH,
} from "./constants.js";
import { fail } from "./errors.js";
import { sha256Hex } from "./hash.js";

const PACKAGE_ROOT_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

export async function readRuntimeManifestSchemaSha256(rootDir = PACKAGE_ROOT_DIR) {
  return await readVendoredSchemaSha256({
    rootDir,
    label: "runtime manifest",
    schemaPath: RUNTIME_MANIFEST_SCHEMA_PATH,
    hashPath: RUNTIME_MANIFEST_SCHEMA_HASH_PATH,
  });
}

export async function readProofBundleSchemaSha256(rootDir = PACKAGE_ROOT_DIR) {
  return await readVendoredSchemaSha256({
    rootDir,
    label: "proof bundle",
    schemaPath: PROOF_BUNDLE_SCHEMA_PATH,
    hashPath: PROOF_BUNDLE_SCHEMA_HASH_PATH,
  });
}

async function readVendoredSchemaSha256(input) {
  const schemaPath = path.join(input.rootDir, input.schemaPath);
  const hashPath = path.join(input.rootDir, input.hashPath);
  let schemaBytes;
  let recordedHashText;
  try {
    [schemaBytes, recordedHashText] = await Promise.all([
      fs.readFile(schemaPath),
      fs.readFile(hashPath, "utf8"),
    ]);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    fail(
      `Replay receiver package is missing vendored ${input.label} schema artifacts: ${detail}`,
      "reinstall @moleculeagora/agora-replay and retry.",
      "schema_artifact_missing",
    );
  }
  const computedHash = sha256Hex(schemaBytes);
  const recordedHash = recordedHashText.trim().split(/\s+/)[0];
  if (computedHash !== recordedHash) {
    fail(
      `Vendored ${input.label} schema hash does not match ${input.hashPath}.`,
      "revendor the Agora main canonical schema artifact and retry.",
      "schema_hash_mismatch",
    );
  }
  return computedHash;
}
