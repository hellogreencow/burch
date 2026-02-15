FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY eidolon_api ./eidolon_api

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "eidolon_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
