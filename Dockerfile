FROM python:3.12-slim

# Create non-root user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy Alembic migration files
COPY alembic.ini alembic/ ./

# Copy scripts
COPY scripts/ ./scripts/

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
