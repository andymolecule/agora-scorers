FROM python:3.11.9-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/Agora" \
      org.opencontainers.image.url="https://github.com/andymolecule/Agora/tree/main/containers/gems-match-scorer" \
      org.opencontainers.image.title="Agora Repro Scorer" \
      org.opencontainers.image.description="Deterministic exact-match scorer for CSV and JSON reproducibility-style presets."

WORKDIR /app
COPY common /app/common
COPY gems-match-scorer /app/gems-match-scorer
CMD ["python", "/app/gems-match-scorer/score.py"]
