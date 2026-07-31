# Repository Structure

```text
app/             Flask application, routes, services, templates, and static files
migrations/      Alembic database migrations
scripts/         PostgreSQL backup and legacy SQLite migration tools
docker/          Dockerfile and entrypoint
tests/           Unit and integration tests
worker.py        Persistent database queue worker entrypoint
wsgi.py          Gunicorn/Flask entrypoint
config.py        Environment-backed application configuration
docker-compose.yml
```

Runtime data and deployment state are intentionally excluded from the
repository.
