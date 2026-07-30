FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]

# gthread workers keep concurrent HTTP requests responsive. Long-running
# backup/restore operations execute in the separate persistent queue worker.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "wsgi:app"]
