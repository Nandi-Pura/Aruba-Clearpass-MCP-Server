# =============================================================================
# Dockerfile — Aruba ClearPass MCP Server
# =============================================================================
# Multi-stage build for a minimal, production-ready SSE transport image.
#
# Build:
#   docker build -t clearpass-mcp .
#
# Run (SSE transport):
#   docker run -p 8000:8000 \
#     -e CLEARPASS_HOST=https://clearpass.yourdomain.com \
#     -e CLEARPASS_CLIENT_ID=your_client_id \
#     -e CLEARPASS_CLIENT_SECRET=your_client_secret \
#     clearpass-mcp
#
# Run (with .env file):
#   docker run -p 8000:8000 --env-file .env clearpass-mcp
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build wheel
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tool
RUN pip install --no-cache-dir hatchling

# Copy only the files needed to build the wheel
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Build the wheel
RUN python -m hatchling build --target wheel


# ---------------------------------------------------------------------------
# Stage 2: Runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1000 mcp && \
    useradd --uid 1000 --gid mcp --no-create-home --shell /bin/false mcp

WORKDIR /app

# Install the wheel from the builder stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Create directory for optional audit log
RUN mkdir -p /var/log/clearpass-mcp && chown mcp:mcp /var/log/clearpass-mcp

# Switch to non-root user
USER mcp

# ---------------------------------------------------------------------------
# Default environment (override at runtime)
# ---------------------------------------------------------------------------
ENV CLEARPASS_HOST=""
ENV CLEARPASS_CLIENT_ID=""
ENV CLEARPASS_CLIENT_SECRET=""
ENV CLEARPASS_VERIFY_SSL="true"
ENV CLEARPASS_READ_ONLY="false"
ENV CLEARPASS_LOG_LEVEL="INFO"
ENV CLEARPASS_AUDIT_LOG_PATH="/var/log/clearpass-mcp/audit.jsonl"
ENV CLEARPASS_MAX_PAGES="20"

EXPOSE 8000

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD clearpass-mcp --check || exit 1

# ---------------------------------------------------------------------------
# Default command: SSE transport
# ---------------------------------------------------------------------------
CMD ["clearpass-mcp", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
