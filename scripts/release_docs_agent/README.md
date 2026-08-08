# Release docs agent launcher

Launches a Cursor cloud agent against [`localangle/backfield-docs`](https://github.com/localangle/backfield-docs)
when Backfield cuts a SemVer release. The agent must follow
`docs/meta/release-update-contract.md` in that repository and open a human-reviewed PR.

## Operator setup

1. Create a Cursor **service-account** API key (or user key) with GitHub connected to
   `localangle/backfield-docs`.
2. Add repository secret `CURSOR_API_KEY` on `localangle/backfield`.
3. SemVer tag pushes run the `docs-sync` job in `.github/workflows/release-artifacts.yml`.
   You can also run that workflow with **workflow_dispatch** and a tag input.

## Local dry run

```bash
cd scripts/release_docs_agent
npm install
export CURSOR_API_KEY=cursor_...
export RELEASE_TAG=v0.8.0
export PREVIOUS_TAG=v0.0.1
export COMMIT_SUMMARY="$(git -C ../.. log --oneline v0.0.1..v0.8.0)"
node launch.mjs
```
