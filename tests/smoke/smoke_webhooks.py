#!/usr/bin/env python3
"""Webhook delivery smoke against a live stack with a local callback receiver.

Covers the golden webhook path end to end:

1. Create a flow and a webhook endpoint subscribed to it (org-admin API).
2. Verify the endpoint with a signed test delivery to a local HTTP receiver.
3. Run the flow and confirm one signed ``agate.run.completed`` delivery.
4. Read the same event from the public event feed and the run-articles endpoint.
5. A second endpoint whose receiver starts failing shows a retry-scheduled delivery.
6. A run from an unsubscribed flow appears in the feed but produces no delivery.

The stack must run with ``BACKFIELD_WEBHOOKS_ENABLED=1`` and
``BACKFIELD_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS=1`` (local Compose defaults).
The containers reach this host through ``SMOKE_WEBHOOK_CALLBACK_HOST``
(default ``host.docker.internal``).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import uuid
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from _helpers import (
    assert_list,
    assert_object,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    wait_for_terminal_run,
)
from backfield_events.signing import verify_webhook_signature

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()
SMOKE_POLL_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_POLL_TIMEOUT_SECONDS", "180"))
SMOKE_POLL_INTERVAL_SECONDS = float(os.environ.get("SMOKE_POLL_INTERVAL_SECONDS", "1.5"))
#: Hostname the Docker containers use to reach this host-side receiver.
CALLBACK_HOST = os.environ.get("SMOKE_WEBHOOK_CALLBACK_HOST", "host.docker.internal").strip()


class _CapturedRequest:
    def __init__(self, path: str, headers: dict[str, str], body: bytes) -> None:
        self.path = path
        self.headers = headers
        self.body = body


class _Receiver:
    """Local callback server. ``/hook`` always 200; ``/flaky`` 200 once, then 500."""

    def __init__(self) -> None:
        self.requests: list[_CapturedRequest] = []
        self._lock = threading.Lock()
        self._flaky_seen = 0

        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server contract
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with receiver._lock:
                    receiver.requests.append(
                        _CapturedRequest(self.path, dict(self.headers.items()), body)
                    )
                    if self.path.startswith("/flaky"):
                        receiver._flaky_seen += 1
                        status = 200 if receiver._flaky_seen == 1 else 500
                    else:
                        status = 200
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def requests_for(self, path_prefix: str) -> list[_CapturedRequest]:
        with self._lock:
            return [r for r in self.requests if r.path.startswith(path_prefix)]

    def wait_for(
        self,
        path_prefix: str,
        *,
        count: int,
        timeout_s: float,
    ) -> list[_CapturedRequest]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rows = self.requests_for(path_prefix)
            if len(rows) >= count:
                return rows
            time.sleep(0.5)
        raise RuntimeError(
            f"Timed out waiting for {count} callback(s) on {path_prefix}; "
            f"got {len(self.requests_for(path_prefix))}"
        )


def _assert_container_can_reach_host() -> None:
    if CALLBACK_HOST == "host.docker.internal":
        with suppress(OSError):
            socket.gethostbyname(CALLBACK_HOST)


def _simple_graph_spec(name: str) -> dict[str, object]:
    return {
        "name": name,
        "nodes": [
            {
                "id": "text",
                "type": "TextInput",
                "params": {"text": "Webhook smoke text."},
                "position": {"x": 0, "y": 0},
            },
            {"id": "out", "type": "Output", "params": {}, "position": {"x": 220, "y": 0}},
        ],
        "edges": [
            {"source": "text", "target": "out", "sourceHandle": "text", "targetHandle": "data"}
        ],
    }


def _verify_signed(request: _CapturedRequest, *, secret: str, context: str) -> dict[str, Any]:
    signature = request.headers.get("Backfield-Signature", "")
    timestamp = request.headers.get("Backfield-Timestamp", "")
    if not verify_webhook_signature(
        secret=secret,
        timestamp=timestamp,
        body=request.body,
        signature=signature,
    ):
        raise RuntimeError(f"{context}: HMAC signature verification failed")
    payload = json.loads(request.body)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context}: expected object body, got {payload!r}")
    return payload


def main() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError("smoke-webhooks requires SMOKE_EMAIL and SMOKE_PASSWORD")

    _assert_container_can_reach_host()
    receiver = _Receiver()
    receiver.start()
    log(f"Callback receiver listening on port {receiver.port} (host {CALLBACK_HOST})")

    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=SMOKE_WORKSPACE_SLUG,
        project_slug=SMOKE_PROJECT_SLUG,
    )
    headers = session_cookie_headers(ctx.session_token)
    org_id = ctx.organization_id
    base_callback = f"http://{CALLBACK_HOST}:{receiver.port}"

    graph_ids: list[str] = []
    endpoint_ids: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    try:
        with (
            httpx.Client(base_url=AGATE_API_BASE, timeout=15.0, headers=headers) as agate,
            httpx.Client(base_url=CORE_API_BASE, timeout=30.0, headers=headers) as core,
        ):
            # 1. Flows: one subscribed, one not.
            subscribed = assert_object(
                agate.post(
                    "/graphs",
                    json={
                        "name": f"Webhook smoke flow {suffix}",
                        "project_id": ctx.project_id,
                        "spec": _simple_graph_spec("webhook_smoke"),
                    },
                ),
                "create subscribed graph",
            )
            graph_ids.append(str(subscribed["id"]))
            unsubscribed = assert_object(
                agate.post(
                    "/graphs",
                    json={
                        "name": f"Webhook smoke unsubscribed {suffix}",
                        "project_id": ctx.project_id,
                        "spec": _simple_graph_spec("webhook_smoke_unsub"),
                    },
                ),
                "create unsubscribed graph",
            )
            graph_ids.append(str(unsubscribed["id"]))

            # 2. Healthy endpoint: create, verify with a signed test, activate.
            created = assert_object(
                core.post(
                    f"/v1/organizations/{org_id}/webhook-endpoints",
                    json={
                        "project_id": ctx.project_id,
                        "name": f"Smoke receiver {suffix}",
                        "url": f"{base_callback}/hook",
                        "flow_ids": [str(subscribed["id"])],
                    },
                ),
                "create endpoint",
            )
            endpoint = created["endpoint"]
            endpoint_ids.append(str(endpoint["id"]))
            secret = str(created["signing_secret"])
            if endpoint["status"] != "pending":
                raise RuntimeError(f"New endpoint should be pending: {endpoint['status']}")

            tested = assert_object(
                core.post(
                    f"/v1/organizations/{org_id}/webhook-endpoints/{endpoint['id']}/test"
                ),
                "verification test",
            )
            if not tested["result"]["ok"] or tested["endpoint"]["status"] != "active":
                raise RuntimeError(f"Verification test failed: {tested['result']}")
            test_request = receiver.wait_for("/hook", count=1, timeout_s=10)[0]
            test_payload = _verify_signed(test_request, secret=secret, context="test delivery")
            if test_payload.get("type") != "backfield.webhook.test":
                raise RuntimeError(f"Unexpected test event type: {test_payload.get('type')}")

            # 3. Flaky endpoint: verification succeeds once, later deliveries get 500.
            flaky_created = assert_object(
                core.post(
                    f"/v1/organizations/{org_id}/webhook-endpoints",
                    json={
                        "project_id": ctx.project_id,
                        "name": f"Smoke flaky receiver {suffix}",
                        "url": f"{base_callback}/flaky",
                        "flow_ids": [str(subscribed["id"])],
                    },
                ),
                "create flaky endpoint",
            )
            flaky_endpoint_id = str(flaky_created["endpoint"]["id"])
            endpoint_ids.append(flaky_endpoint_id)
            flaky_tested = assert_object(
                core.post(
                    f"/v1/organizations/{org_id}/webhook-endpoints/{flaky_endpoint_id}/test"
                ),
                "flaky verification test",
            )
            if flaky_tested["endpoint"]["status"] != "active":
                raise RuntimeError("Flaky endpoint failed to activate")

            # 4. Run the subscribed flow; expect one signed completion delivery.
            run = assert_object(
                agate.post("/runs", json={"graph_id": str(subscribed["id"])}),
                "create run",
            )
            terminal = wait_for_terminal_run(
                agate,
                str(run["id"]),
                timeout_s=SMOKE_POLL_TIMEOUT_SECONDS,
                interval_s=SMOKE_POLL_INTERVAL_SECONDS,
            )
            if terminal.get("status") != "succeeded":
                raise RuntimeError(f"Run did not succeed: {terminal.get('status')}")

            completion_request = receiver.wait_for("/hook", count=2, timeout_s=60)[1]
            envelope = _verify_signed(
                completion_request, secret=secret, context="run-completed delivery"
            )
            if envelope.get("type") != "agate.run.completed":
                raise RuntimeError(f"Unexpected event type: {envelope.get('type')}")
            if envelope.get("run", {}).get("id") != str(run["id"]):
                raise RuntimeError(f"Delivery for wrong run: {envelope.get('run')}")
            if envelope.get("data", {}).get("outcome") != "succeeded":
                raise RuntimeError(f"Unexpected outcome: {envelope.get('data')}")

            # 5. The flaky endpoint's delivery should be retry-scheduled after a 500.
            receiver.wait_for("/flaky", count=2, timeout_s=60)
            deadline = time.time() + 30
            flaky_delivery: dict[str, Any] | None = None
            while time.time() < deadline:
                deliveries = assert_list(
                    core.get(
                        f"/v1/organizations/{org_id}/webhook-endpoints/"
                        f"{flaky_endpoint_id}/deliveries"
                    ),
                    "flaky deliveries",
                )
                flaky_delivery = next(
                    (row for row in deliveries if not row.get("is_test")), None
                )
                if flaky_delivery and flaky_delivery.get("failure_category"):
                    break
                time.sleep(1)
            if flaky_delivery is None:
                raise RuntimeError("No non-test delivery recorded for flaky endpoint")
            if flaky_delivery["state"] not in ("pending", "delivering"):
                raise RuntimeError(
                    f"Expected flaky delivery to be retry-scheduled: {flaky_delivery['state']}"
                )
            if flaky_delivery["failure_category"] != "http_5xx":
                raise RuntimeError(
                    f"Unexpected failure category: {flaky_delivery['failure_category']}"
                )

            # 6. Public pull contract: feed and run-articles via a project API key.
            key = assert_object(
                core.post(
                    f"/v1/projects/{ctx.project_id}/api-keys",
                    json={"credential_type": "user", "label": f"webhook-smoke-{suffix}"},
                ),
                "create project API key",
            )
            api_headers = {"Authorization": f"Bearer {key['raw_key']}"}
            feed = assert_object(
                core.get(
                    f"/public/v1/projects/{ctx.project_slug}/events",
                    headers=api_headers,
                    params={"flow_id": str(subscribed["id"])},
                ),
                "event feed",
            )
            feed_runs = [item.get("run", {}).get("id") for item in feed.get("items", [])]
            if str(run["id"]) not in feed_runs:
                raise RuntimeError(f"Run event missing from feed: {feed_runs}")

            articles = assert_object(
                core.get(
                    f"/public/v1/projects/{ctx.project_slug}/runs/{run['id']}/articles",
                    headers=api_headers,
                ),
                "run articles",
            )
            if articles.get("attempt") != 1:
                raise RuntimeError(f"Expected attempt 1: {articles.get('attempt')}")

            # 7. Unsubscribed flow: feed event, no webhook delivery.
            hook_count_before = len(receiver.requests_for("/hook"))
            unsub_run = assert_object(
                agate.post("/runs", json={"graph_id": str(unsubscribed["id"])}),
                "create unsubscribed run",
            )
            unsub_terminal = wait_for_terminal_run(
                agate,
                str(unsub_run["id"]),
                timeout_s=SMOKE_POLL_TIMEOUT_SECONDS,
                interval_s=SMOKE_POLL_INTERVAL_SECONDS,
            )
            if unsub_terminal.get("status") != "succeeded":
                raise RuntimeError("Unsubscribed run did not succeed")

            deadline = time.time() + 30
            unsub_seen = False
            while time.time() < deadline and not unsub_seen:
                unsub_feed = assert_object(
                    core.get(
                        f"/public/v1/projects/{ctx.project_slug}/events",
                        headers=api_headers,
                        params={"flow_id": str(unsubscribed["id"])},
                    ),
                    "unsubscribed feed",
                )
                unsub_seen = any(
                    item.get("run", {}).get("id") == str(unsub_run["id"])
                    for item in unsub_feed.get("items", [])
                )
                if not unsub_seen:
                    time.sleep(1)
            if not unsub_seen:
                raise RuntimeError("Unsubscribed run event missing from feed")
            time.sleep(3)
            if len(receiver.requests_for("/hook")) != hook_count_before:
                raise RuntimeError("Unsubscribed flow produced an unexpected delivery")

            log("Smoke webhooks passed.")
            log(f"Project: {ctx.project_slug} ({ctx.project_id})")
            log(f"Run: {run['id']}  Endpoint: {endpoint['id']}")
            return 0
    finally:
        with suppress(Exception):
            with httpx.Client(
                base_url=CORE_API_BASE, timeout=15.0, headers=headers
            ) as core_cleanup:
                if not keep_smoke_data():
                    for endpoint_id in endpoint_ids:
                        with suppress(Exception):
                            core_cleanup.delete(
                                f"/v1/organizations/{org_id}/webhook-endpoints/{endpoint_id}"
                            )
        with suppress(Exception):
            with httpx.Client(
                base_url=AGATE_API_BASE, timeout=15.0, headers=headers
            ) as agate_cleanup:
                if not keep_smoke_data():
                    for graph_id in graph_ids:
                        with suppress(Exception):
                            agate_cleanup.delete(f"/graphs/{graph_id}")
        receiver.stop()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
