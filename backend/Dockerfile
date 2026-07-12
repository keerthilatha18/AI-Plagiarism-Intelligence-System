# ─────────────────────────────────────────────────────────────────────────────
# Plagiarism Intelligence — backend Dockerfile
# Base: python:3.11-slim for a minimal production image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install OS-level deps needed by pdfminer / spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

# Copy application code
COPY . .

# Expose port (IBM Code Engine default)
EXPOSE 8080

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
