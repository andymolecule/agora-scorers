import fs from "node:fs";
import yaml from "yaml";

const workflowPath = ".github/workflows/publish.yml";
const workflow = yaml.parse(fs.readFileSync(workflowPath, "utf8"));

function fail(message) {
  throw new Error(
    `${message} Next step: keep the scorer release artifact bound to GitHub provenance so Agora main digest rotation can enforce source integrity.`,
  );
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    fail(`${label} expected ${JSON.stringify(expected)} but found ${JSON.stringify(actual)}.`);
  }
}

function assertArrayIncludes(values, expected, label) {
  if (!Array.isArray(values) || !values.includes(expected)) {
    fail(`${label} must include ${JSON.stringify(expected)}.`);
  }
}

function findStep(job, label) {
  const step = job?.steps?.find((candidate) => candidate.name === label);
  if (!step) {
    fail(`Missing workflow step ${JSON.stringify(label)}.`);
  }
  return step;
}

const publishJob = workflow.jobs?.publish;
if (!publishJob) {
  fail("Missing publish job.");
}

const testJob = workflow.jobs?.test;
if (!testJob) {
  fail("Missing test job.");
}

const pullRequestTrigger = workflow.on?.pull_request;
if (!pullRequestTrigger) {
  fail("Publish workflow must run the non-publishing test lane on pull_request.");
}
for (const path of [
  "schema/**",
  "scripts/**",
  "package.json",
  "package-lock.json",
  ".github/workflows/publish.yml",
]) {
  assertArrayIncludes(
    pullRequestTrigger.paths,
    path,
    "pull_request path filter",
  );
}

assertEqual(
  publishJob.if,
  "github.event_name != 'pull_request'",
  "publish job pull_request guard",
);
assertEqual(publishJob.permissions?.contents, "read", "publish contents permission");
assertEqual(publishJob.permissions?.packages, "write", "publish packages permission");
assertEqual(publishJob.permissions?.["id-token"], "write", "publish id-token permission");
assertEqual(
  publishJob.permissions?.attestations,
  "write",
  "publish attestations permission",
);
assertEqual(
  publishJob.permissions?.["artifact-metadata"],
  "write",
  "publish artifact-metadata permission",
);

findStep(testJob, "Run release provenance check");
findStep(testJob, "Run RDKit image smoke");

const requireAgoraTokenStep = findStep(testJob, "Require Agora repo read token");
assertEqual(
  requireAgoraTokenStep.if,
  "github.event_name != 'pull_request'",
  "Agora token preflight pull_request guard",
);
if (
  !requireAgoraTokenStep.run?.includes("AGORA_REPO_READ_TOKEN is required") ||
  !requireAgoraTokenStep.run?.includes("exit 1")
) {
  fail("Agora token preflight must fail closed before non-PR publish checks.");
}

const checkoutAgoraSchemaStep = findStep(
  testJob,
  "Checkout Agora canonical runtime manifest schema",
);
assertEqual(
  checkoutAgoraSchemaStep.if,
  "github.event_name != 'pull_request'",
  "Agora schema checkout pull_request guard",
);
assertEqual(
  checkoutAgoraSchemaStep.uses,
  "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
  "Agora schema checkout action",
);
assertEqual(
  checkoutAgoraSchemaStep.with?.repository,
  "moleculeprotocol/Agora",
  "Agora schema checkout repository",
);
assertEqual(checkoutAgoraSchemaStep.with?.ref, "main", "Agora schema checkout ref");
assertEqual(
  checkoutAgoraSchemaStep.with?.token,
  "${{ secrets.AGORA_REPO_READ_TOKEN }}",
  "Agora schema checkout token",
);
assertEqual(
  checkoutAgoraSchemaStep.with?.["sparse-checkout"],
  "packages/common/src/schemas/scorer-runtime-manifest.canonical.schema.json",
  "Agora schema checkout sparse path",
);

const verifyAgoraSchemaStep = findStep(
  testJob,
  "Verify vendored schema matches Agora main",
);
assertEqual(
  verifyAgoraSchemaStep.if,
  "github.event_name != 'pull_request'",
  "Agora schema sync pull_request guard",
);
assertEqual(
  verifyAgoraSchemaStep.env?.AGORA_MAIN_RUNTIME_MANIFEST_SCHEMA_PATH,
  "${{ github.workspace }}/agora-main/packages/common/src/schemas/scorer-runtime-manifest.canonical.schema.json",
  "Agora schema sync path",
);
assertEqual(
  verifyAgoraSchemaStep.run,
  "npm run check:agora-main-schema-sync",
  "Agora schema sync command",
);

const buildStep = findStep(publishJob, "Build and push ${{ matrix.name }}");
assertEqual(
  buildStep.with?.provenance,
  "mode=max",
  "docker/build-push-action provenance mode",
);
const matrixRows = publishJob.strategy?.matrix?.include ?? [];
const compiledRuntimeRow = matrixRows.find(
  (row) => row.name === "agora-scorer-compiled",
);
const rdkitRuntimeRow = matrixRows.find((row) => row.name === "agora-scorer-rdkit");
assertEqual(
  compiledRuntimeRow?.profile_id,
  "official_compiled_runtime",
  "compiled runtime matrix profile_id",
);
assertEqual(
  compiledRuntimeRow?.supported_program_abi_versions,
  "python-v1",
  "compiled runtime matrix ABI list",
);
assertEqual(
  compiledRuntimeRow?.determinism_env_json,
  '{"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PYTHONHASHSEED":"0","SOURCE_DATE_EPOCH":"0","TZ":"UTC"}',
  "compiled runtime matrix determinism env",
);
assertEqual(
  rdkitRuntimeRow?.profile_id,
  "rdkit_python_runtime",
  "RDKit runtime matrix profile_id",
);
assertEqual(
  rdkitRuntimeRow?.supported_program_abi_versions,
  "python-v1",
  "RDKit runtime matrix ABI list",
);
assertEqual(
  rdkitRuntimeRow?.determinism_env_json,
  '{"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PYTHONHASHSEED":"0","SOURCE_DATE_EPOCH":"0","TZ":"UTC"}',
  "RDKit runtime matrix determinism env",
);

const attestStep = findStep(publishJob, "Attest ${{ matrix.name }} image provenance");
assertEqual(
  attestStep.uses,
  "actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26",
  "pinned actions/attest action",
);
assertEqual(
  attestStep.with?.["subject-name"],
  "ghcr.io/${{ env.GHCR_NAMESPACE }}/${{ matrix.name }}",
  "attestation subject-name",
);
assertEqual(
  attestStep.with?.["subject-digest"],
  "${{ steps.build-push.outputs.digest }}",
  "attestation subject-digest",
);
assertEqual(attestStep.with?.["push-to-registry"], true, "attestation registry push");

const exportStep = findStep(publishJob, "Export release metadata");
const releaseArtifactFields = [
  '"profile_id": "${{ matrix.profile_id }}"',
  '"runtime_manifest_schema_sha256": "${{ steps.contract-metadata.outputs.runtime_manifest_schema_sha256 }}"',
  '"determinism_env_sha256": "${{ steps.contract-metadata.outputs.determinism_env_sha256 }}"',
  '"provenance"',
  '"predicate_type": "https://slsa.dev/provenance/v1"',
  '"subject_name": "ghcr.io/${{ env.GHCR_NAMESPACE }}/${{ matrix.name }}"',
  '"subject_digest": "${{ steps.build-push.outputs.digest }}"',
  '"source_repository": "${{ github.repository }}"',
  '"source_ref": "${{ github.ref }}"',
  '"source_commit": "${{ github.sha }}"',
  '"signer_workflow": "${{ github.repository }}/.github/workflows/publish.yml"',
  '"attestation_id": "${{ steps.attest.outputs[\'attestation-id\'] }}"',
  '"attestation_url": "${{ steps.attest.outputs[\'attestation-url\'] }}"',
];

for (const field of releaseArtifactFields) {
  if (!exportStep.run?.includes(field)) {
    fail(`official-runtime-release.json does not include ${field}.`);
  }
}

const metadataStep = findStep(publishJob, "Read runtime contract metadata");
const metadataScript = metadataStep.run ?? "";
if (
  !metadataScript.includes(
    "runtime_manifest_schema_sha256=\"$(sha256sum schema/scorer-runtime-manifest.canonical.schema.json | cut -d ' ' -f1)\"",
  ) ||
  !metadataScript.includes(
    "recorded_schema_sha256=\"$(cut -d ' ' -f1 schema/scorer-runtime-manifest.canonical.sha256)\"",
  ) ||
  !metadataScript.includes(
    'if [ "$runtime_manifest_schema_sha256" != "$recorded_schema_sha256" ]; then',
  )
) {
  fail(
    "Publish workflow must prove runtime_manifest_schema_sha256 equals the vendored canonical schema hash before exporting release metadata.",
  );
}

console.log("release provenance workflow check passed");
