FROM python:3.11.9-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/agora-scorers" \
      org.opencontainers.image.url="https://github.com/andymolecule/agora-scorers/tree/main/agora-scorer-table-metric" \
      org.opencontainers.image.title="Agora Table Metric Scorer" \
      org.opencontainers.image.description="Deterministic table metric scorer for regression and classification challenges."

WORKDIR /app
COPY common /app/common
COPY agora-scorer-table-metric /app/agora-scorer-table-metric
CMD ["python", "/app/agora-scorer-table-metric/score.py"]
