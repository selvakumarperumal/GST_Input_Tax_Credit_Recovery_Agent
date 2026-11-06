# Build from the repo root:  docker build -f src/gst_input_tax_credit_recovery_agent/Dockerfile .

FROM python:3.15-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/

ENV UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app

# COPY <source on host, relative to the build context = repo root> <destination in image>
COPY pyproject.toml uv.lock /app/
COPY src/gst_input_tax_credit_recovery_agent /app/src/gst_input_tax_credit_recovery_agent

# Install only this app, exactly as pinned in uv.lock.
# --frozen (not --locked): other workspace packages aren't in this image, so uv can't re-check the lock.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package gst-input-tax-credit-recovery-agent

RUN useradd --system app
USER app

EXPOSE 8000
CMD ["uvicorn", "gst_input_tax_credit_recovery_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
