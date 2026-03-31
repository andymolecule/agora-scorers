FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/Agora" \
      org.opencontainers.image.url="https://github.com/andymolecule/Agora/tree/main/containers/gems-ranking-scorer" \
      org.opencontainers.image.title="Agora Docking Scorer" \
      org.opencontainers.image.description="Deterministic docking scorer image family for Agora docking presets."

WORKDIR /app
COPY score.py /app/score.py
CMD ["python", "/app/score.py"]
