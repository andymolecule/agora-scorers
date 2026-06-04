FROM python:3.11.9-slim@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

LABEL org.opencontainers.image.source="https://github.com/moleculeprotocol/agora-scorers" \
      org.opencontainers.image.description="Agora official compiled deterministic scorer runtime" \
      org.opencontainers.image.url="https://github.com/moleculeprotocol/agora-scorers/tree/main/agora-scorer-compiled" \
      org.opencontainers.image.licenses="MIT AND GPL-3.0-or-later" \
      agora.runtime-profile-id="official_compiled_runtime" \
      agora.base-image="python:3.11.9-slim@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317" \
      agora.system-package.perl="5.36.0-7+deb12u3" \
      agora.system-package.perl-base="5.36.0-7+deb12u3" \
      agora.system-package.perl-modules-5.36="5.36.0-7+deb12u3" \
      agora.system-package.libperl5.36="5.36.0-7+deb12u3" \
      agora.system-package.libgdbm-compat4="1.23-3" \
      agora.python-package.toxinpred3="1.4" \
      agora.python-package.scikit-learn="1.2.2" \
      agora.python-package.pandas="2.2.3" \
      agora.python-package.numpy="1.26.4" \
      agora.python-package.scipy="1.11.4"

WORKDIR /app

COPY agora-scorer-compiled/requirements.txt /tmp/agora-scorer-compiled-requirements.txt
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libgdbm-compat4=1.23-3 \
      libperl5.36=5.36.0-7+deb12u3 \
      perl=5.36.0-7+deb12u3 \
      perl-base=5.36.0-7+deb12u3 \
      perl-modules-5.36=5.36.0-7+deb12u3; \
    rm -rf /var/lib/apt/lists/*; \
    python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --only-binary=:all: \
      --progress-bar=off \
      --require-hashes \
      --retries 10 \
      --timeout 120 \
      -r /tmp/agora-scorer-compiled-requirements.txt; \
    rm /tmp/agora-scorer-compiled-requirements.txt

COPY common /app/common
COPY agora-scorer-compiled /app/agora-scorer-compiled

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/common:/app/agora-scorer-compiled

CMD ["python", "/app/agora-scorer-compiled/entrypoint.py"]
