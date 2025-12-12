# Build stage - optimized multi-stage build
FROM python:3.13-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --user .

# Final stage - minimal runtime image
FROM python:3.13-slim

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Set user
USER appuser

# Add user's local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

# Health check (optional)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=2 \
    CMD python -c "import sys; sys.exit(0)"

ENTRYPOINT ["python", "main.py"]
