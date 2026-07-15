FROM postgres:16-bookworm

# PostGIS, pgvector (semantic embeddings), and H3 spatial indexing.
# Prefer the official multi-arch Postgres image so Apple Silicon hosts run
# natively. The older postgis/postgis:16-3.4 tag is amd64-only and forces
# QEMU on arm64, which makes postgres healthchecks hang during `compose up`.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      postgresql-16-postgis-3 \
      postgresql-16-postgis-3-scripts \
      postgresql-16-pgvector \
      postgresql-16-h3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
