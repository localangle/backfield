FROM postgis/postgis:16-3.4

# pgvector for semantic document embeddings (revision 038_substrate_semantic_docs).
# postgresql-16-h3 for H3 spatial indexing (revision 048_location_h3).
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-pgvector postgresql-16-h3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
