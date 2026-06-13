FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user — required by Cloud Run best practices and many org policies.
# /tmp is world-writable so start.sh can still write credential files there.
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    chown -R appuser:appgroup /app && \
    chmod +x start.sh

USER appuser

EXPOSE 8000

CMD ["/bin/sh", "start.sh"]
