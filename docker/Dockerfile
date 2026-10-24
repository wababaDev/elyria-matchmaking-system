FROM python:3.11-slim

# Match your local `poetry --version`
ARG POETRY_VERSION=2.1.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# PDF generation (WeasyPrint) needs Pango, plus fonts
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

# Dependencies first, so code changes don't reinstall everything
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . .

# collectstatic loads production settings, so give it throwaway values (build only)
RUN SECRET_KEY=build-only \
    ALLOWED_HOSTS=localhost \
    CSRF_TRUSTED_ORIGINS=http://localhost \
    DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    python manage.py collectstatic --noinput

# Run as a normal user, not root
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/media \
    && chmod +x /app/docker/entrypoint.sh \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]