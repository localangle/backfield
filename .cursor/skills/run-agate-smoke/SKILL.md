---
name: run-agate-smoke
description: Validate the Backfield golden path against a live stack. Use when runtime behavior changes across Agate API, worker, Stylebook API, or the four-node starter flow.
---

# Run Agate Smoke

## Quick Start

1. Ensure the stack is running.
2. Run `make smoke`.
3. If it fails, inspect `make logs` and the relevant service logs.

## What The Smoke Covers

- Agate API health
- Stylebook API health
- Temp project creation
- Template instantiation into a graph
- Run enqueue on the `agate` queue
- Worker completion and terminal run status
- Cleanup of smoke-created resources

## When To Use It

- Queue, worker, or run lifecycle changes
- API contract changes that affect graphs, templates, projects, or runs
- Stylebook geocode integration changes
- DB changes that affect the live runtime path
