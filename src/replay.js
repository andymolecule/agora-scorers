import { createHash } from "node:crypto";
import { SUPPORTED_PROGRAM_ABI_VERSIONS } from "./constants.js";
import { parseWithNextAction, proofBundleSchema } from "./contracts.js";
import { fetchJson } from "./fetch.js";
import { hashProofBundleCid } from "./hash.js";
import {
  readProofBundleSchemaSha256,
  readRuntimeManifestSchemaSha256,
} from "./schema-hash.js";

export function computeDeterminismEnvSha256(determinismEnv) {
  const canonical = Object.fromEntries(
    Object.entries(determinismEnv).sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
  return createHash("sha256").update(JSON.stringify(canonical)).digest("hex");
}

export async function replayProof(options) {
  const [runtimeManifestSchemaSha256, proofBundleSchemaSha256] =
    await Promise.all([
      readRuntimeManifestSchemaSha256(),
      readProofBundleSchemaSha256(),
    ]);
  const proof = parseWithNextAction(
    proofBundleSchema,
    await fetchJson(options.proof, options.ipfsGateway),
    "proof bundle",
    "use a current optimistic-private Agora proof CID with score_proof_facts.",
  );
  const proofHash = hashProofBundleCid(options.proof);
  const proofHashMatches = options.expectedProofHash
    ? proofHash.toLowerCase() === options.expectedProofHash.toLowerCase()
    : null;
  const mismatches =
    proofHashMatches === false
      ? [
          {
            field: "proof_hash",
            expected: options.expectedProofHash,
            actual: proofHash,
          },
        ]
      : [];

  return {
    status:
      mismatches.length === 0 ? "not_publicly_replayable" : "mismatched",
    reason:
      mismatches.length === 0
        ? "private_answer_not_publicly_replayable"
        : "proof_hash_mismatch",
    replay_available: false,
    replay_scope: "challenge_reveal_only",
    score: proof.score,
    proof_cid: options.proof,
    proof_hash: proofHash,
    proof_hash_matches: proofHashMatches,
    challenge_spec_cid: proof.challenge_spec_cid,
    runtime_profile_id: proof.score_proof_facts.scoring_profile_id,
    image_digest: proof.container_image_digest,
    score_proof_facts: proof.score_proof_facts,
    runtime_manifest_schema_sha256: runtimeManifestSchemaSha256,
    proof_bundle_schema_sha256: proofBundleSchemaSha256,
    supported_program_abi_versions: SUPPORTED_PROGRAM_ABI_VERSIONS,
    mismatches,
    next_action:
      "Non-challenged optimistic-private proofs do not publish answer replay inputs. Use Agora challenge-by-reveal evidence for public re-score verification after a solver voluntarily reveals a committed answer.",
  };
}
