FROM python:3.11.9-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/Agora" \
      org.opencontainers.image.url="https://github.com/andymolecule/Agora/tree/main/containers/gems-tabular-scorer" \
      org.opencontainers.image.title="Agora Regression Scorer" \
      org.opencontainers.image.description="Deterministic regression scorer for Agora prediction presets."

WORKDIR /app
COPY common /app/common
COPY gems-tabular-scorer /app/gems-tabular-scorer
CMD ["python", "/app/gems-tabular-scorer/score.py"]
