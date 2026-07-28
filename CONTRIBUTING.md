# Contributing to Backfield

Thank you for your interest in contributing. This guide is the human entry point for
external contributors. Agent and engineering conventions live in [AGENTS.md](AGENTS.md).

## Project status

This repository supports **local development and source inspection**. Production
self-hosting from this checkout is **not supported** today. Contributions that improve
local workflows, documentation, APIs, UIs, and packaging are welcome; please do not open
PRs that assume an in-repo production deploy path.

## Ways to contribute

- Bug reports and reproductions
- Documentation fixes and clarifications
- Small, focused code changes with tests
- Features that fit existing package boundaries (see [architecture overview](docs/architecture/overview.md))

Larger ideas should start as a [feature request](https://github.com/localangle/backfield/issues/new?template=feature_request.yml) or discussion so maintainers can align on scope before a large PR.

## Before you start

1. Read this file and the [Code of Conduct](CODE_OF_CONDUCT.md).
2. Skim [Project status](#project-status) above and [local setup](docs/development/local-setup.md).
3. For repository map, commands, and validation defaults, use [AGENTS.md](AGENTS.md).
4. Search existing issues and pull requests for duplicates.

## Development setup

Prerequisites: Python 3.11, Docker Engine with Compose v2, [uv](https://docs.astral.sh/uv/),
and Node.js 20 for UI work outside Docker.

```bash
git clone https://github.com/localangle/backfield.git
cd backfield
make bootstrap
source .venv/bin/activate
backfield init
backfield doctor
```

`backfield init` creates local secrets, starts Compose, runs migrations, and seeds the first
administrator. After init, configure model credentials in **Settings → AI models**. Full detail:
[Local development setup](docs/development/local-setup.md).

Stack shortcuts:

| Goal | Command |
| --- | --- |
| Start | `make up` / `backfield up` |
| Stop (project-scoped; does not prune Docker globally) | `make down` / `backfield down` |
| Migrate (Compose one-off service) | `make migrate` |
| Migrate (host CLI against local Postgres) | `make migrate-host` |
| Opt-in Docker cleanup | `make docker-trim` |

## Making changes

1. Fork [localangle/backfield](https://github.com/localangle/backfield) and create a branch from `main`.
2. Keep the diff focused on one problem.
3. Prefer existing Make/`backfield` CLI targets over inventing new command flows.
4. Update the matching source-of-truth doc under `docs/` when behavior or operations change.
5. Follow package boundaries in [docs/architecture/overview.md](docs/architecture/overview.md).

Do not add HTTP or environment-variable “bootstrap admin” paths. First-admin provisioning is
`backfield init` / `backfield seed` only.

## Validation

Before opening a PR:

```bash
make lint
make test
```

Also run when relevant:

```bash
make ui-typecheck ui-test   # UI/TypeScript changes
make ui-build               # production UI bundles
make smoke-fast             # live stack, no provider keys required
make smoke                  # golden-path handoff; needs configured AI models
```

See [Testing](docs/development/testing.md) for layout and the fork-safe CI contract.

## Pull requests

- Fill out the PR template.
- Link the related issue when one exists.
- Describe intent, risk, and how you validated the change.
- Keep commits reviewable; force-pushes are fine on your feature branch before merge.

Maintainers may ask for smaller PRs, extra tests, or doc updates before merge.

## Reporting security issues

Do **not** open a public issue for vulnerabilities. Use GitHub private vulnerability reporting
as described in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE.md). Copyright for the project is held by Local Angle (2026)
and contributors under the terms of that license.

## Questions

- Product and platform docs: [docs.backfield.news](https://docs.backfield.news)
- Repository docs index: [docs/README.md](docs/README.md)
- Community conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) (`opensource@localangle.co`)
