FROM python:3.11.9-slim@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

LABEL org.opencontainers.image.source="https://github.com/moleculeprotocol/agora-scorers" \
      org.opencontainers.image.description="Agora RDKit Python deterministic scorer runtime" \
      org.opencontainers.image.url="https://github.com/moleculeprotocol/agora-scorers/tree/main/agora-scorer-rdkit" \
      org.opencontainers.image.licenses="MIT AND Apache-2.0" \
      agora.runtime-profile-id="rdkit_python_runtime" \
      agora.base-image="python:3.11.9-slim@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317" \
      agora.python-package.rdkit="2025.3.1" \
      agora.python-package.numpy="2.4.4" \
      agora.python-package.pillow="12.2.0" \
      agora.python-package.xgboost-cpu="3.0.5" \
      agora.python-package.pandas="2.3.3" \
      agora.python-package.scipy="1.17.1" \
      agora.python-package.joblib="1.5.3" \
      agora.opensol.source-repository="https://github.com/sutropub/OpenSOL" \
      agora.opensol.source-commit="89e6d30d0ce84aaf9ee2bd9c93619d3c2a4a95c4" \
      agora.opensol.model-path="/opt/agora/opensol/Models/xgboost_rdkit_2d_clustering_model.json" \
      agora.opensol.model-sha256="bb0e4c542c8172b717239f62be3d538bf1ede214a385af055411c02f1d928da0"

WORKDIR /app

COPY agora-scorer-rdkit/requirements.txt /tmp/agora-scorer-rdkit-requirements.txt
RUN python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --only-binary=:all: \
      --require-hashes \
      -r /tmp/agora-scorer-rdkit-requirements.txt \
    && rm /tmp/agora-scorer-rdkit-requirements.txt

COPY common /app/common
COPY agora-scorer-compiled /app/agora-scorer-compiled
COPY agora-scorer-rdkit/opensol /opt/agora/opensol

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/common:/app/agora-scorer-compiled
ENV OPENSOL_HOME=/opt/agora/opensol

CMD ["python", "/app/agora-scorer-compiled/entrypoint.py"]
