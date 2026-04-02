FROM python:3.11.9-slim

LABEL org.opencontainers.image.source="https://github.com/andymolecule/Agora" \
      org.opencontainers.image.url="https://github.com/andymolecule/Agora/tree/main/containers/gems-code-executor" \
      org.opencontainers.image.title="Agora Code Executor" \
      org.opencontainers.image.description="Deterministic Python code execution scorer for Agora pass-rate challenges."

WORKDIR /app
COPY common /app/common
COPY gems-code-executor /app/gems-code-executor
CMD ["python", "/app/gems-code-executor/score.py"]
