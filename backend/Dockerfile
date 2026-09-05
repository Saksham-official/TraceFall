# Multi-stage: the build stage carries a compiler for any wheel that needs one, and none
# of it reaches the runtime image.
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# The build context is the repository root, not backend/, because the image needs
# config/ and data/ which live above it. Every path below is repo-root-relative.
WORKDIR /srv
COPY backend/pyproject.toml ./
COPY backend/app ./app
# Installed into a virtualenv rather than the system interpreter so the runtime stage
# copies one directory and inherits nothing else.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /srv
COPY --from=build /opt/venv /opt/venv

# The application package, and the four things it reads at runtime. Every one of these
# was previously missing from the image, and each failed a different documented step:
#
#   alembic/, alembic.ini     `alembic upgrade head` — the first thing the operator runs
#   config/risk_weights.yaml  the RISK stage, on every analysis
#   data/labels/              `load-labels`, and therefore every CONFIRMED attribution
#   tests/fixtures/           LIVE_MODE=false, which is the default and the demo path
#
# They are located by search at runtime (app/core/paths.py), so the working directory
# below is what makes them findable.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY config ./config
COPY data ./data
COPY backend/tests/fixtures ./tests/fixtures

# Non-root, and owning the directories it writes to. A bind or volume mount over a path
# the image did not create arrives root-owned, and the write fails at the first report.
RUN useradd --create-home --uid 10001 tracefall \
    && mkdir -p /data/evidence /data/reports \
    && chown -R tracefall:tracefall /data /srv
USER tracefall

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
