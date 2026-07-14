# Backfield

Backfield is a platform for turning unstructured news articles into structured, reusable editorial data.

## Key applications

Backfield is composed of three interconnected applications:

### Agate

Agate allows users to build workflows that extract arbitrary data from articles and enrich them with useful metadata. It also includes a robust human review interface, which editors can use to refine and correct the results.

### Stylebook

Stylebook serves as a canonical store of people, places and organizations that appear across an organization's coverage. It helps standardize entities into trustworthy objects that can be further enriched with metadata and connected to each other.

### Chronicle

Chronicle is an editorial intelligence tool that allows users to explore YYY.

## Quick start

You need [Docker and Docker Compose](https://docs.docker.com/compose/) and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:localangle/backfield.git
cd backfield
make bootstrap               # uv sync + install project launcher into .venv/bin
source .venv/bin/activate    # once per shell
backfield init               # set up env, start the stack, migrate, and seed
```

`backfield` is a **project launcher** (shell wrapper at `scripts/backfield`), not a Python package entry point. Bootstrap copies it to `.venv/bin/backfield` so it is available after you activate the venv. You can also run `./scripts/backfield` or `make up` without activating.

Optional — use `backfield` from any directory without activating the venv:

```bash
make install-user-cli        # symlinks ~/.local/bin/backfield -> scripts/backfield
backfield up                 # requires ~/.local/bin on PATH
```

Run `backfield doctor` to verify repo root, uv, Docker, `.venv`, and `.env`.

`backfield init` walks you through first-run setup and, when it finishes, opens the app in your browser:

- Agate: [http://localhost:5173](http://localhost:5173)
- Stylebook: [http://localhost:5175](http://localhost:5175)

To manage the stack afterward, use `backfield up`, `backfield down`, `backfield logs`, or `make up` / `make down` / `make logs`.

## Hosted release artifacts

Every successful `main` CI run publishes one immutable Linux/AMD64 release unit:

- four container images tagged `main-<12-char-sha>-amd64`
- deterministic Agate and Stylebook UI archives
- checksums, ECR digests, source SHA, scan results, and build metadata in one manifest

Publishing does not deploy to a client. `backfield-cloud` explicitly promotes a manifest version.
Creating a strict `vX.Y.Z` Git tag on a commit already on `main` adds ECR aliases and a release
manifest without rebuilding any artifact. Neither `latest` nor mutable branch tags are published.

Repository variables required by the workflows are `AWS_ARTIFACT_PUBLISHER_ROLE_ARN`,
`BACKFIELD_ARTIFACT_BUCKET`, and `AWS_REGION`.

## License

Copyright 2026 Local Angle

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this
software except in compliance with the License. You may obtain a copy of the License
in [LICENSE.md](LICENSE.md) or at
[apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

## Support

Questions or issues? See [docs.backfield.news](https://docs.backfield.news) or open an issue in this repository.