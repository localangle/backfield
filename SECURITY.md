# Security policy

## Supported use

Backfield in this repository is intended for **local development and source inspection**.
Production self-hosting from this checkout is not a supported security boundary today.
Still, we treat reported vulnerabilities seriously so local users and future deployers
are not exposed unnecessarily.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Use GitHub’s private vulnerability reporting for
[localangle/backfield](https://github.com/localangle/backfield):

1. Open the repository’s **Security** tab.
2. Choose **Report a vulnerability** (or “Advisories” → “New draft advisory” / report flow,
   depending on GitHub’s UI).
3. Include enough detail for maintainers to reproduce and assess impact:
   - affected component (API, worker, UI, CLI, package)
   - versions or commit SHA if known
   - steps to reproduce
   - impact and any known mitigations

If private reporting is unavailable, contact maintainers at **opensource@localangle.co**
with the subject line `Security report: Backfield` and the same details. Do not include
exploit payloads that are broader than needed for reproduction.

## What to expect

- Acknowledgement when a maintainer can triage the report
- Coordination on disclosure timing when a fix is prepared
- Credit in the advisory when you want it, unless you request anonymity

We may decline reports that are purely speculative, require unsupported production
self-hosting assumptions, or are already fixed on `main`.

## Non-security bugs

Use a [bug report](https://github.com/localangle/backfield/issues/new?template=bug_report.yml)
for non-security defects. See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution process.
