# Backfield

> **Turn the reporting you publish into knowledge you can use.**

Backfield helps newsrooms turn unstructured stories into organized, reusable editorial data. It finds the people, places, organizations, and other facts in an article; gives editors a clear place to review the results; and connects approved records across the organization’s coverage.

It is built for the work that happens after publication: understanding who and what your newsroom has covered, correcting the record, and building a reliable foundation for future reporting.

<p align="center">
  <img src="assets/screenshots/agate-flow-builder.png" alt="An Agate flow that extracts and enriches editorial data from an article" width="100%">
</p>

## What you can do with Backfield

| | |
| --- | --- |
| **Build repeatable editorial workflows** | Use a visual flow builder to decide what to extract or enrich from one story or a whole batch. |
| **Review results with source context** | See every result alongside the passage that produced it, then correct, remove, or add information before it becomes part of your record. |
| **Maintain a shared Stylebook** | Bring mentions of the same person, place, or organization together in a canonical record that grows with your coverage. |
| **Make your coverage usable** | Keep structured results available for editorial tools, analysis, and the public API. |

## How it fits together

```text
Stories  →  Agate flows  →  Editor review  →  Stylebook  →  Reusable data
```

- **Agate** is the workspace for building flows, processing articles, and reviewing the results.
- **Stylebook** is the shared record of the people, places, and organizations that matter to your coverage.
- **The public API** makes approved, structured data available to products and reporting tools.

The goal is not to replace editorial judgment. Backfield makes automated extraction useful by keeping people in control of the results.

<p align="center">
  <img src="assets/screenshots/article-review-places.png" alt="Backfield's article review screen, with highlighted place mentions, a map, and editable results" width="100%">
</p>

## Start locally

### What you need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Compose included)
- [uv](https://docs.astral.sh/uv/) for Python dependencies
- Git

### Get running

```bash
git clone git@github.com:localangle/backfield.git
cd backfield
make bootstrap
source .venv/bin/activate
backfield init
```

`backfield init` guides you through local setup, creates the development environment, starts the services, runs database migrations, and seeds a local administrator. When it finishes, open:

| App | Local address | Use it for |
| --- | --- | --- |
| **Agate** | [localhost:5173](http://localhost:5173) | Building flows and reviewing article results |
| **Stylebook** | [localhost:5175](http://localhost:5175) | Browsing and curating shared records |

> **Already set up?** Run `backfield up` to start the stack, `backfield logs` to follow service logs, and `backfield down` when you are done. `make up`, `make logs`, and `make down` provide the same shortcuts.

### Check your setup

```bash
backfield doctor
```

This verifies that Docker, `uv`, the local environment, and configuration are ready. For the
full workflow, see [Local development setup](docs/development/local-setup.md); for common
failures, see [Troubleshooting](docs/operations/troubleshooting.md).

## Learn more

- [A five-step example: from a story to reusable data](https://docs.backfield.news/platform/simple-example/)
- [Agate flows and processing](https://docs.backfield.news/platform/agate/)
- [Stylebook and canonical records](https://docs.backfield.news/platform/stylebook/)
- [Public API guide](docs/api/public.md)
- [Architecture](docs/architecture/overview.md)
- [Repository documentation](docs/README.md)
- [All documentation](https://docs.backfield.news)

## For contributors

This repository is a monorepo containing the Agate and Stylebook applications, their APIs, a background worker, and shared packages. Start with [AGENTS.md](AGENTS.md) for the repository map and development commands. Use `make lint` and `make test` before submitting changes.

## License

Copyright 2026 Local Angle

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this
software except in compliance with the License. You may obtain a copy of the License
in [LICENSE.md](LICENSE.md) or at
[apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).

## Support

Questions or issues? See [docs.backfield.news](https://docs.backfield.news) or open an issue in this repository.