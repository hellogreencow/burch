FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY eidolon_worker ./eidolon_worker

RUN pip install --no-cache-dir .

CMD ["python", "-m", "eidolon_worker.main"]
