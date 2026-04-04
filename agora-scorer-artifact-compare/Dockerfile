FROM python:3.11.9-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/agora-scorers" \
      org.opencontainers.image.url="https://github.com/andymolecule/agora-scorers/tree/main/agora-scorer-artifact-compare" \
      org.opencontainers.image.title="Agora Artifact Compare Scorer" \
      org.opencontainers.image.description="Deterministic exact-match and structured-validation scorer for artifact comparison challenges."

WORKDIR /app
COPY common /app/common
COPY agora-scorer-artifact-compare /app/agora-scorer-artifact-compare
CMD ["python", "/app/agora-scorer-artifact-compare/score.py"]
