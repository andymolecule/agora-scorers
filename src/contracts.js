import { createHash } from "node:crypto";
import { z } from "zod";
import { fail } from "./errors.js";

const hexSha256Schema = z.string().regex(/^[a-f0-9]{64}$/);
const hexBytes32Schema = z.string().regex(/^0x[a-fA-F0-9]{64}$/);
const trimmedStringSchema = z.string().trim().min(1);
const uriSchema = z.string().trim().min(1);
const ipfsOrHttpsUriSchema = trimmedStringSchema.refine(
  (value) => value.startsWith("ipfs://") || /^https:\/\/\S+$/.test(value),
  "value must start with ipfs:// or be a valid https:// URL",
);
const artifactRoleSchema = trimmedStringSchema.regex(/^[a-z][a-z0-9_]*$/);
const scoringAssetKindSchema = z.enum(["program", "config", "bundle", "document"]);
const OPTIMISTIC_PRIVATE_SCORING_MODEL = "optimistic_private_scoring";

function normalizeJsonValue(value) {
  if (Array.isArray(value)) {
    return value.map((entry) => normalizeJsonValue(entry));
  }
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, normalizeJsonValue(entry)]),
    );
  }
  return value;
}

function sha256Hex32(preimage) {
  return `0x${createHash("sha256").update(JSON.stringify(normalizeJsonValue(preimage))).digest("hex")}`;
}

export function computeScoreBasisCommitment(input) {
  return sha256Hex32({
    challenge_spec_cid: input.challengeSpecCid,
    container_image_digest: input.containerImageDigest,
    kind: "score_basis_commitment",
    private_input_commitment: input.privateInputCommitment,
    runtime_manifest_digest: input.runtimeManifestDigest,
    scoring_model: OPTIMISTIC_PRIVATE_SCORING_MODEL,
    scoring_profile_id: input.scoringProfileId,
  });
}

const scoreProofFactsSchema = z
  .object({
    kind: z.literal("score_proof_facts"),
    scoring_profile_id: trimmedStringSchema,
    score_basis_commitment: hexBytes32Schema,
    runtime_manifest_digest: hexSha256Schema,
    private_input_commitment: hexBytes32Schema,
    artifact_digest_policy: z.literal("private_no_public_equality_digest"),
  })
  .strict();

export const proofBundleSchema = z
  .object({
    score: z.number().finite(),
    container_image_digest: trimmedStringSchema,
    scorer_log: z.string().optional(),
    challenge_spec_cid: ipfsOrHttpsUriSchema,
    score_proof_facts: scoreProofFactsSchema,
    measurement_provenance_receipts: z.array(z.unknown()).optional(),
    meta: z
      .object({
        challenge_id: trimmedStringSchema,
        submission_id: trimmedStringSchema,
      })
      .strict(),
  })
  .strict()
  .superRefine((proof, ctx) => {
    const expectedScoreBasisCommitment = computeScoreBasisCommitment({
      challengeSpecCid: proof.challenge_spec_cid,
      containerImageDigest: proof.container_image_digest,
      runtimeManifestDigest: proof.score_proof_facts.runtime_manifest_digest,
      scoringProfileId: proof.score_proof_facts.scoring_profile_id,
      privateInputCommitment: proof.score_proof_facts.private_input_commitment,
    });
    if (
      proof.score_proof_facts.score_basis_commitment.toLowerCase() !==
      expectedScoreBasisCommitment
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["score_proof_facts", "score_basis_commitment"],
        message:
          "score_basis_commitment must match challenge_spec_cid, container_image_digest, runtime_manifest_digest, scoring_profile_id, and private_input_commitment",
      });
    }
  });

const artifactFileSchema = z
  .object({
    extension: trimmedStringSchema.optional(),
    mime_type: trimmedStringSchema.optional(),
    max_bytes: z.number().int().positive(),
  })
  .strict();

const artifactValidatorSchema = z
  .object({
    kind: trimmedStringSchema,
  })
  .passthrough();

const artifactSlotSchema = z
  .object({
    role: artifactRoleSchema,
    required: z.boolean(),
    description: trimmedStringSchema,
    file: artifactFileSchema,
    validator: artifactValidatorSchema,
  })
  .strict();

const artifactContractSchema = z
  .object({
    evaluation: z.array(artifactSlotSchema),
    submission: z.array(artifactSlotSchema).min(1),
    relations: z.array(z.object({ kind: trimmedStringSchema }).passthrough()).default([]),
  })
  .strict();

const runtimeProfileSchema = z
  .object({
    kind: z.literal("official"),
    profile_id: trimmedStringSchema,
    image: trimmedStringSchema,
    limits: z
      .object({
        memory: trimmedStringSchema,
        cpus: trimmedStringSchema,
        pids: z.number().int().positive(),
        timeoutMs: z.number().int().positive(),
      })
      .strict(),
    supported_program_abi_versions: z.array(trimmedStringSchema).default([]),
    determinism_env: z.record(trimmedStringSchema),
  })
  .strict();

const evaluationBindingSchema = z
  .object({
    kind: z.literal("artifact"),
    role: artifactRoleSchema,
    artifact_id: trimmedStringSchema,
  })
  .strict();

const scoringAssetSourceSchema = z
  .object({
    role: trimmedStringSchema,
    kind: scoringAssetKindSchema,
    artifact_id: trimmedStringSchema,
    abi_version: trimmedStringSchema.optional(),
    entrypoint: trimmedStringSchema.optional(),
    uri: uriSchema,
    file_name: trimmedStringSchema.optional(),
    mime_type: trimmedStringSchema.optional(),
    size_bytes: z.number().int().nonnegative(),
    sha256: hexSha256Schema,
  })
  .strict();

const scoringAssetRefSchema = z
  .object({
    role: trimmedStringSchema,
    kind: scoringAssetKindSchema,
    artifact_id: trimmedStringSchema,
    abi_version: trimmedStringSchema.optional(),
    entrypoint: trimmedStringSchema.optional(),
    file_name: trimmedStringSchema.optional(),
    mime_type: trimmedStringSchema.optional(),
  })
  .strict();

const scorerResultFieldSchema = z.union([
  trimmedStringSchema.transform((key) => ({ key, value_type: "number" })),
  z
    .object({
      key: trimmedStringSchema,
      label: trimmedStringSchema.optional(),
      value_type: z.enum(["number", "integer", "string", "boolean"]).default("number"),
      description: trimmedStringSchema.optional(),
    })
    .strict(),
]);

export const scorerResultSchema = z
  .object({
    dimensions: z.array(scorerResultFieldSchema).default([]),
    bonuses: z.array(scorerResultFieldSchema).default([]),
    penalties: z.array(scorerResultFieldSchema).default([]),
    summary_fields: z.array(scorerResultFieldSchema).default([]),
    allow_additional_details: z.boolean().default(true),
  })
  .strict();

export const scorerOutputEnvelopeSchema = z.discriminatedUnion("ok", [
  z
    .object({
      ok: z.literal(true),
      score: z.number().finite().nonnegative(),
      details: z.record(z.unknown()).default({}),
      error: z.string().optional(),
    })
    .strict(),
  z
    .object({
      ok: z.literal(false),
      score: z.number().finite().nonnegative().default(0),
      details: z.record(z.unknown()).default({}),
      error: trimmedStringSchema,
    })
    .strict(),
]);

export const challengeSpecSchema = z
  .object({
    schema_version: z.union([z.literal(5), z.literal(6)]),
    id: trimmedStringSchema,
    execution: z
      .object({
        runtime_profile: runtimeProfileSchema,
        artifact_contract: artifactContractSchema,
        evaluation_bindings: z.array(evaluationBindingSchema),
        scoring_asset_sources: z.array(scoringAssetSourceSchema).default([]),
        scoring_assets: z.array(scoringAssetRefSchema).default([]),
        objective: z.enum(["maximize", "minimize"]),
        final_score_key: trimmedStringSchema,
        scorer_result_schema: scorerResultSchema,
        policies: z
          .object({
            coverage_policy: z.enum(["reject", "ignore", "penalize"]).default("ignore"),
            duplicate_id_policy: z.enum(["reject", "ignore"]).default("ignore"),
            invalid_value_policy: z.enum(["reject", "ignore"]).default("ignore"),
          })
          .strict()
          .default({
            coverage_policy: "ignore",
            duplicate_id_policy: "ignore",
            invalid_value_policy: "ignore",
          }),
      })
      .strict(),
    artifacts: z
      .array(
        z
          .object({
            artifact_id: trimmedStringSchema,
            role: trimmedStringSchema,
            visibility: z.enum(["public", "private"]),
            uri: uriSchema.optional(),
            file_name: trimmedStringSchema.optional(),
            mime_type: trimmedStringSchema.optional(),
            description: trimmedStringSchema.optional(),
            size_bytes: z.number().int().nonnegative().optional(),
            sha256: hexSha256Schema.optional(),
            timelock_commitment: z.object({}).passthrough().optional(),
          })
          .strict(),
      )
      .default([]),
  })
  .passthrough();

export const cliOptionsSchema = z
  .object({
    proof: trimmedStringSchema,
    format: z.enum(["json"]).default("json"),
    ipfsGateway: trimmedStringSchema,
    expectedProofHash: hexBytes32Schema.optional(),
    workDir: trimmedStringSchema.optional(),
    keepWorkspace: z.boolean().default(false),
  })
  .strict();

export function parseWithNextAction(schema, value, label, nextAction) {
  const result = schema.safeParse(value);
  if (result.success) {
    return result.data;
  }
  const message = result.error.issues
    .map((issue) => `${issue.path.join(".") || label}: ${issue.message}`)
    .join("; ");
  fail(`${label} validation failed: ${message}.`, nextAction, "validation_failed");
}

export function listScorerResultFields(schema) {
  return ["dimensions", "bonuses", "penalties", "summary_fields"].flatMap((section) =>
    schema[section].map((field) => ({ ...field, section })),
  );
}

function isDeclaredValueType(value, valueType) {
  if (valueType === "number") {
    return typeof value === "number" && Number.isFinite(value);
  }
  if (valueType === "integer") {
    return Number.isInteger(value);
  }
  if (valueType === "string") {
    return typeof value === "string";
  }
  return typeof value === "boolean";
}

function describeValue(value) {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return "array";
  }
  return typeof value;
}

export function validateScorerResultDetailsAgainstSchema(schema, details) {
  const declaredFields = listScorerResultFields(schema);
  const declaredKeys = new Set(declaredFields.map((field) => field.key));
  const errors = [];

  for (const field of declaredFields) {
    if (!(field.key in details)) {
      errors.push(`details.${field.key} is required by scorer_result_schema.${field.section}.`);
      continue;
    }
    const value = details[field.key];
    if (!isDeclaredValueType(value, field.value_type)) {
      errors.push(`details.${field.key} must be ${field.value_type}, received ${describeValue(value)}.`);
    }
  }

  if (!schema.allow_additional_details) {
    for (const key of Object.keys(details)) {
      if (!declaredKeys.has(key)) {
        errors.push(`details.${key} is not declared in scorer_result_schema and allow_additional_details is false.`);
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
