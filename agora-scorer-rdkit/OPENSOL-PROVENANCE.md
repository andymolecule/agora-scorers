# OpenSOL Runtime Provenance

The `rdkit_python_runtime` image vendors the public OpenSOL prediction assets
for Agora's standalone `opensol_solubility@1` scorer.

- Source repository: `https://github.com/sutropub/OpenSOL`
- Source commit: `89e6d30d0ce84aaf9ee2bd9c93619d3c2a4a95c4`
- Upstream license file: `LICENSE.txt`, Apache-2.0 notice by Sutro Biopharma
- Bundled model path:
  `opensol/Models/xgboost_rdkit_2d_clustering_model.json`
- Bundled model SHA-256:
  `bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0`

Source hashes:

- Upstream `opensol/Scripts/solubility_model.py` before the Agora
  prediction-only patch:
  `9eb282a2a1ada18390034f7908bf7ba300b9961639e8b08f074c4aad09317d83`
- Bundled `opensol/Scripts/solubility_model.py` after the Agora
  prediction-only patch and line-ending normalization:
  `a29ace3e9b7d8b2bef5f0cb7d88aaccf0378bbbed9de8b0df47bdcd9ea5977c2`
- Upstream `opensol/Scripts/Tools.py` before the Agora prediction-only patch:
  `a74d39e043fb69ce1112fe94879f5a74fbc95e3fa8d652cd88e3e53ae47bbe67`
- Bundled `opensol/Scripts/Tools.py` after the Agora prediction-only patch:
  and line-ending normalization:
  `4e10b240fc209e2d916a90c1faec97930ab56e409c146a813117104dd72b256a`
- Upstream `opensol/LICENSE.txt` before line-ending normalization:
  `f208265d4bc52ff02a71045d87455eab7b066dad2b33a443a381eab8c5946416`
- Bundled `opensol/LICENSE.txt` after line-ending normalization:
  `8ffec4c17335dc96b8c5e4679bb31905b0e51435d55bd80466eb69210c61fa61`

The Agora image supports the fixed OpenSOL prediction mode used by
`opensol_solubility@1`: `Prediction -m xgboost -dscr rdkit_2d -s clustering`.
It does not bundle OpenSOL training data, CCDC/CSD-derived datasets, notebooks,
DNN weights, random-forest assets, or alternate model artifacts. The patched
`solubility_model.py` builds the prediction molecule column with
`Chem.MolFromSmiles` instead of RDKit `PandasTools` so the slim runtime does
not require OS drawing libraries. It also gates the RDKit descriptor matrix to
the pinned XGBoost model's declared `num_feature` count and fails closed if
RDKit provides too few descriptors. The patched `Tools.py` leaves
DNN/training-only helpers unavailable in this image instead of adding unused
PyTorch or scikit-learn dependencies.
