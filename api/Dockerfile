FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir hatchling \
    && pip wheel --no-cache-dir --wheel-dir=/wheels -e .

FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r biocoach && useradd -r -g biocoach biocoach

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY api/ ./api/
COPY prompts/ ./prompts/

USER biocoach

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
