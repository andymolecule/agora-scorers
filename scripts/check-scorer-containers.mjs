import fs from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";

const rootDir = process.cwd();
const maxEmbeddedAssetBytes = 1_000_000;
const disallowedAssetPattern =
  /\.(csv|tsv|jsonl|parquet|arrow|feather|npy|npz|pt|pth|ckpt|onnx|pkl|pickle|joblib|bin|h5|hdf5|tar|tgz|gz|bz2|xz|zip)$/i;

const scorerDirs = ["agora-scorer-compiled", "agora-scorer-rdkit"];
const compiledRequirementsPath = path.join(
  rootDir,
  "agora-scorer-compiled",
  "requirements.txt",
);
const rdkitRequirementsPath = path.join(
  rootDir,
  "agora-scorer-rdkit",
  "requirements.txt",
);
const disallowedRequirementPattern =
  /\b(scanpy|scvelo|biopython|biotite|dock|jupyter|notebook|torch|tensorflow|sklearn|scikit-learn)\b/i;
const disallowedCompiledRequirementPattern =
  /\b(scanpy|scvelo|biopython|biotite|dock|jupyter|notebook|torch|tensorflow|opensol|aggrescan|boltz)\b/i;
const opensolSourceCommit = "89e6d30d0ce84aaf9ee2bd9c93619d3c2a4a95c4";
const opensolModelRelativePath =
  "agora-scorer-rdkit/opensol/Models/xgboost_rdkit_2d_clustering_model.json";
const allowedEmbeddedAssets = new Map([
  [
    opensolModelRelativePath,
    {
      maxBytes: 2_000_000,
      sha256: "bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0",
    },
  ],
]);
const opensolPinnedFiles = new Map([
  [
    "agora-scorer-rdkit/opensol/Scripts/solubility_model.py",
    "a29ace3e9b7d8b2bef5f0cb7d88aaccf0378bbbed9de8b0df47bdcd9ea5977c2",
  ],
  [
    "agora-scorer-rdkit/opensol/Scripts/Tools.py",
    "4e10b240fc209e2d916a90c1faec97930ab56e409c146a813117104dd72b256a",
  ],
  [
    "agora-scorer-rdkit/opensol/LICENSE.txt",
    "8ffec4c17335dc96b8c5e4679bb31905b0e51435d55bd80466eb69210c61fa61",
  ],
  [
    opensolModelRelativePath,
    "bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0",
  ],
]);

function fail(message) {
  throw new Error(
    `${message} Next step: keep scorer images limited to code plus explicitly allowlisted runtime assets, and move hidden evaluation artifacts or large assets into the evaluation bundle mounted at runtime.`,
  );
}

function sha256(filePath) {
  return createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function relativeToRoot(filePath) {
  return path.relative(rootDir, filePath).split(path.sep).join("/");
}

function walkFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(fullPath));
      continue;
    }
    if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function validateDockerfile(dockerfilePath) {
  const dockerfile = fs.readFileSync(dockerfilePath, "utf8");
  const lines = dockerfile.split("\n");

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    if (/^ADD\s+/i.test(line)) {
      fail(
        `Dockerfile ${path.relative(rootDir, dockerfilePath)} uses ADD, which is disallowed for official scorers.`,
      );
    }

    const copyMatch = /^COPY\s+(.+)$/i.exec(line);
    if (!copyMatch) continue;

    const instruction = copyMatch[1]
      .split(/\s+/)
      .filter((part) => !part.startsWith("--"));

    if (instruction.length < 2) continue;

    const sources = instruction.slice(0, -1);
    for (const source of sources) {
      if (source.includes("..")) {
        fail(
          `Dockerfile ${path.relative(rootDir, dockerfilePath)} copies from outside its scorer directory (${source}).`,
        );
      }
      const relativeSource = source.split(path.sep).join("/");
      if (
        disallowedAssetPattern.test(source) &&
        !allowedEmbeddedAssets.has(relativeSource)
      ) {
        fail(
          `Dockerfile ${path.relative(rootDir, dockerfilePath)} copies dataset-like asset ${source}.`,
        );
      }
    }
  }
}

function validateContainerDir(containerDir) {
  const dockerfilePath = path.join(containerDir, "Dockerfile");
  if (!fs.existsSync(dockerfilePath)) {
    fail(`Missing Dockerfile in ${path.relative(rootDir, containerDir)}.`);
  }

  validateDockerfile(dockerfilePath);

  const files = walkFiles(containerDir);
  for (const filePath of files) {
    const relativePath = relativeToRoot(filePath);
    const stats = fs.statSync(filePath);
    const allowedAsset = allowedEmbeddedAssets.get(relativePath);

    if (allowedAsset) {
      if (stats.size > allowedAsset.maxBytes) {
        fail(
          `Allowlisted runtime asset ${relativePath} is ${stats.size} bytes, which exceeds ${allowedAsset.maxBytes} bytes.`,
        );
      }
      if (sha256(filePath) !== allowedAsset.sha256) {
        fail(`Allowlisted runtime asset ${relativePath} does not match its pinned SHA-256.`);
      }
      continue;
    }

    if (stats.size > maxEmbeddedAssetBytes) {
      fail(
        `Scorer file ${relativePath} is ${stats.size} bytes, which exceeds the code-only policy threshold of ${maxEmbeddedAssetBytes} bytes.`,
      );
    }

    if (disallowedAssetPattern.test(filePath)) {
      fail(`Scorer directory contains dataset-like asset ${relativePath}.`);
    }
  }
}

function validateRdkitRequirements() {
  if (!fs.existsSync(rdkitRequirementsPath)) {
    fail("Missing agora-scorer-rdkit/requirements.txt.");
  }
  const requirements = fs.readFileSync(rdkitRequirementsPath, "utf8");
  for (const expected of [
    "rdkit==2025.3.1",
    "numpy==2.4.4",
    "Pillow==12.2.0",
    "xgboost==3.0.5",
    "pandas==2.3.3",
    "scipy==1.17.1",
    "joblib==1.5.3",
    "python-dateutil==2.9.0.post0",
    "pytz==2025.2",
    "tzdata==2025.2",
    "six==1.17.0",
  ]) {
    if (!requirements.includes(expected)) {
      fail(`RDKit requirements must include exact pin ${expected}.`);
    }
  }
  if (!requirements.includes("--hash=sha256:")) {
    fail("RDKit requirements must use hash-locked package pins.");
  }
  if (disallowedRequirementPattern.test(requirements)) {
    fail("RDKit requirements include a broad or out-of-scope science package.");
  }
}

function validateOpenSolAssets() {
  const opensolDir = path.join(rootDir, "agora-scorer-rdkit", "opensol");
  if (!fs.existsSync(opensolDir)) {
    fail("Missing pinned OpenSOL runtime assets for rdkit_python_runtime.");
  }
  const datasetsDir = path.join(opensolDir, "Datasets");
  if (fs.existsSync(datasetsDir)) {
    fail("OpenSOL runtime assets must not bundle Datasets/ or CCDC/CSD-derived data.");
  }
  for (const [relativePath, expectedHash] of opensolPinnedFiles.entries()) {
    const filePath = path.join(rootDir, relativePath);
    if (!fs.existsSync(filePath)) {
      fail(`Missing pinned OpenSOL file ${relativePath}.`);
    }
    const actualHash = sha256(filePath);
    if (actualHash !== expectedHash) {
      fail(
        `Pinned OpenSOL file ${relativePath} SHA-256 mismatch: expected ${expectedHash}, found ${actualHash}.`,
      );
    }
  }

  const dockerfile = fs.readFileSync(
    path.join(rootDir, "agora-scorer-rdkit", "Dockerfile"),
    "utf8",
  );
  const modelHash = opensolPinnedFiles.get(opensolModelRelativePath);
  for (const expected of [
    `agora.opensol.source-commit="${opensolSourceCommit}"`,
    `agora.opensol.model-sha256="${modelHash}"`,
  ]) {
    if (!dockerfile.includes(expected)) {
      fail(`RDKit Dockerfile must record OpenSOL provenance label ${expected}.`);
    }
  }

  const provenancePath = path.join(rootDir, "agora-scorer-rdkit", "OPENSOL-PROVENANCE.md");
  if (!fs.existsSync(provenancePath)) {
    fail("Missing agora-scorer-rdkit/OPENSOL-PROVENANCE.md.");
  }
  const provenance = fs.readFileSync(provenancePath, "utf8");
  for (const expected of [opensolSourceCommit, modelHash, "Prediction -m xgboost -dscr rdkit_2d -s clustering"]) {
    if (!provenance.includes(expected)) {
      fail(`OpenSOL provenance must include ${expected}.`);
    }
  }
}

function validateCompiledRequirements() {
  if (!fs.existsSync(compiledRequirementsPath)) {
    fail("Missing agora-scorer-compiled/requirements.txt.");
  }
  const requirements = fs.readFileSync(compiledRequirementsPath, "utf8");
  for (const expected of [
    "toxinpred3==1.4",
    "scikit-learn==1.2.2",
    "pandas==2.2.3",
    "numpy==1.26.4",
    "scipy==1.11.4",
  ]) {
    if (!requirements.includes(expected)) {
      fail(`Compiled requirements must include exact pin ${expected}.`);
    }
  }
  if (!requirements.includes("--hash=sha256:")) {
    fail("Compiled requirements must use hash-locked package pins.");
  }
  if (disallowedCompiledRequirementPattern.test(requirements)) {
    fail("Compiled requirements include an out-of-scope science package.");
  }
}

for (const name of scorerDirs) {
  const containerDir = path.join(rootDir, name);
  if (!fs.existsSync(containerDir)) {
    fail(`${name}/ directory not found.`);
  }
  validateContainerDir(containerDir);
}

validateRdkitRequirements();
validateOpenSolAssets();
validateCompiledRequirements();

console.log("scorer container guard passed");
