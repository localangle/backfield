FROM postgis/postgis:16-3.4

# pgvector for semantic document embeddings (revision 038_substrate_semantic_docs).
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
