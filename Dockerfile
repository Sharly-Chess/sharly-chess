FROM python:3.13-slim

# Build dependencies for native extensions (cryptography, argon2-cffi, aiosqlite, ...)
# and for toga's Linux backend (toga-gtk -> pycairo + PyGObject), which is a
# hard dependency of `toga` on Linux even though the container runs headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libffi-dev \
        libssl-dev \
        libcairo2-dev \
        libgirepository-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY default-files ./default-files
COPY locale ./locale
COPY docker-entrypoint.sh ./

# Editable-less install: build backend needs the package layout present, so
# dependencies are installed via the project metadata directly.
RUN pip install --no-cache-dir .

# Pre-fetch the front-end libraries and pairing tools (bbpPairings,
# papi-converter) and compile the .mo translation catalogs, so the image is
# self-contained and the first container start doesn't need network access.
# PYTHONPATH makes this resolve `common`/`web`/... from ./src rather than the
# copy pip installed alongside the third-party dependencies, so BASE_DIR
# resolves to /app instead of the site-packages location.
RUN PYTHONPATH=/app/src python scripts/libs/install_libs.py \
    && rm -rf /app/dev-data

# Federation-specific plugins (FFE, FIDE, Chess-Results) each need their own
# private credentials to even be imported in a packaged (non-dev) build; we
# don't have those, so the container intentionally keeps running in the
# app's dev/unfrozen mode (DEVEL_ENV=True, see src/common/__init__.py) where
# those plugins degrade to a startup warning instead of a hard failure.
# Lets Client._get_account() (src/data/access_levels/client.py) also trust
# the container's default gateway as the local/administrator machine, since
# Docker's bridge networking otherwise hides the real 127.0.0.1 of a host
# request behind that gateway address (NAT hairpin).
ENV TZ=UTC \
    SHARLY_CHESS_DOCKER=1

RUN mkdir -p /data && chmod +x docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["./docker-entrypoint.sh"]
