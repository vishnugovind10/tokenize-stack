FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY services ./services
COPY stackctl ./stackctl
RUN python -m pip install --no-cache-dir -e .
CMD ["python", "-m", "stackctl", "demo"]
