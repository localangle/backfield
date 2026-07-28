## Summary

<!-- What changed and why? Link related issues when applicable. -->

## Project scope check

- [ ] This change targets local development / source inspection (production self-hosting is unsupported in this repo)
- [ ] Docs under `docs/` updated if behavior, architecture, or operations changed
- [ ] First-admin provisioning still uses `backfield init` / `backfield seed` only (no HTTP/env bootstrap paths)

## Test plan

- [ ] `make lint`
- [ ] `make test`
- [ ] `make ui-typecheck ui-test` (if UI/TypeScript changed)
- [ ] `make smoke-fast` (if live-stack behavior changed)
- [ ] `make smoke` (if golden-path / provider-dependent runtime changed; configure **Settings → AI models**)

## Notes for reviewers

<!-- Risk, rollout concerns, follow-ups, or screenshots. -->
