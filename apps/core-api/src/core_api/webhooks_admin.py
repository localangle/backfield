"""Org-admin webhook endpoint management (domain logic for the router).

Endpoints are project-scoped; URLs and signing secrets are encrypted at rest and
the plaintext secret is returned exactly once on create/rotate. New and rewired
endpoints stay ``pending`` until a signed test delivery receives a 2xx.
"""

from __future__ import annotations

import json
import secrets as _secrets
from datetime import UTC, datetime
from typing import Literal

from backfield_db import (
    AgateGraph,
    BackfieldEvent,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookDeliveryAttempt,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
)
from backfield_db.crypto import decrypt_secret, encrypt_secret
from backfield_events.contracts import RUN_COMPLETED_EVENT
from backfield_events.destinations import (
    WebhookDestinationError,
    display_host_for_url,
    validate_webhook_url,
)
from backfield_events.recording import (
    DELIVERY_STATE_FAILED,
    DELIVERY_STATE_PENDING,
    ENDPOINT_STATUS_ACTIVE,
    ENDPOINT_STATUS_DISABLED,
    ENDPOINT_STATUS_PAUSED,
    ENDPOINT_STATUS_PENDING,
)
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func
from sqlmodel import Session, col, select

MAX_ACTIVE_ENDPOINTS_PER_PROJECT = 10
VALID_OUTCOMES = ("succeeded", "failed")

WebhookOutcome = Literal["succeeded", "failed"]


# ----- Response / request models -----


class WebhookFlowOut(BaseModel):
    flow_id: str
    flow_name: str | None


class WebhookEndpointOut(BaseModel):
    id: str
    project_id: int
    project_name: str | None
    project_slug: str | None
    name: str
    destination_host: str
    status: str
    secret_version: int
    verified_at: datetime | None
    paused_at: datetime | None
    pause_reason: str | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    outcomes: list[WebhookOutcome] | None
    flows: list[WebhookFlowOut]
    pending_deliveries: int
    failed_deliveries: int
    created_at: datetime
    updated_at: datetime


class WebhookEndpointCreateBody(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1)
    flow_ids: list[str] = Field(min_length=1)
    outcomes: list[WebhookOutcome] | None = None


class WebhookEndpointCreatedOut(BaseModel):
    endpoint: WebhookEndpointOut
    #: Shown exactly once; store it in the receiving application.
    signing_secret: str


class WebhookEndpointPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = None
    flow_ids: list[str] | None = Field(default=None, min_length=1)
    outcomes: list[WebhookOutcome] | None = None
    clear_outcomes: bool = False


class WebhookSecretOut(BaseModel):
    #: Shown exactly once; store it in the receiving application.
    signing_secret: str
    secret_version: int
    endpoint: WebhookEndpointOut


class WebhookDeliveryAttemptOut(BaseModel):
    attempt_number: int
    attempted_at: datetime
    status_code: int | None
    failure_category: str | None
    failure_summary: str | None
    duration_ms: int | None


class WebhookDeliveryOut(BaseModel):
    id: str
    event_id: str
    event_type: str
    flow_name: str | None
    run_id: str | None
    state: str
    attempt_count: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    failure_category: str | None
    failure_summary: str | None
    is_replay: bool
    is_test: bool
    created_at: datetime
    delivered_at: datetime | None
    attempts: list[WebhookDeliveryAttemptOut]


# ----- Helpers -----


def generate_signing_secret() -> str:
    return f"whsec_{_secrets.token_urlsafe(32)}"


def _require_project_in_org(session: Session, org_id: int, project_id: int) -> BackfieldProject:
    project = session.get(BackfieldProject, project_id)
    if project is None or int(project.organization_id) != int(org_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in this organization",
        )
    return project


def _require_flows_in_project(
    session: Session,
    project_id: int,
    flow_ids: list[str],
) -> dict[str, AgateGraph]:
    cleaned = [flow_id.strip() for flow_id in flow_ids if flow_id.strip()]
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose at least one flow",
        )
    graphs: dict[str, AgateGraph] = {}
    for flow_id in dict.fromkeys(cleaned):
        graph = session.get(AgateGraph, flow_id)
        if graph is None or int(graph.project_id) != int(project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow not found in the selected project",
            )
        graphs[flow_id] = graph
    return graphs


def _validated_url(url: str) -> str:
    """Shape/scheme/literal-address checks at save time; DNS is checked per delivery."""
    try:
        return validate_webhook_url(url, resolve_dns=False).url
    except WebhookDestinationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"That destination can't be used: {e.reason}",
        ) from e


def _outcomes_json(outcomes: list[str] | None) -> str | None:
    if not outcomes:
        return None
    cleaned = [value for value in dict.fromkeys(outcomes) if value in VALID_OUTCOMES]
    if not cleaned or len(cleaned) == len(VALID_OUTCOMES):
        return None
    return json.dumps(cleaned)


def require_webhook_endpoint(
    session: Session,
    org_id: int,
    endpoint_id: str,
) -> BackfieldWebhookEndpoint:
    endpoint = session.get(BackfieldWebhookEndpoint, endpoint_id)
    if endpoint is None or int(endpoint.organization_id) != int(org_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found",
        )
    return endpoint


def _enforce_endpoint_limit(session: Session, project_id: int) -> None:
    count = int(
        session.exec(
            select(func.count())
            .select_from(BackfieldWebhookEndpoint)
            .where(
                BackfieldWebhookEndpoint.project_id == project_id,
                BackfieldWebhookEndpoint.status != ENDPOINT_STATUS_DISABLED,
            )
        ).one()
    )
    if count >= MAX_ACTIVE_ENDPOINTS_PER_PROJECT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This project already has {MAX_ACTIVE_ENDPOINTS_PER_PROJECT} webhook "
                "endpoints. Remove or turn off one before adding another."
            ),
        )


def _replace_subscriptions(
    session: Session,
    endpoint: BackfieldWebhookEndpoint,
    flow_ids: list[str],
    outcomes_json: str | None,
) -> None:
    session.exec(
        delete(BackfieldWebhookSubscription).where(
            BackfieldWebhookSubscription.endpoint_id == endpoint.id
        )
    )
    for flow_id in dict.fromkeys(flow_ids):
        session.add(
            BackfieldWebhookSubscription(
                endpoint_id=endpoint.id,
                event_type=RUN_COMPLETED_EVENT,
                graph_id=flow_id,
                outcomes_json=outcomes_json,
            )
        )


def endpoint_to_out(session: Session, endpoint: BackfieldWebhookEndpoint) -> WebhookEndpointOut:
    project = session.get(BackfieldProject, endpoint.project_id)
    subscriptions = session.exec(
        select(BackfieldWebhookSubscription).where(
            BackfieldWebhookSubscription.endpoint_id == endpoint.id
        )
    ).all()
    flows: list[WebhookFlowOut] = []
    outcomes: list[str] | None = None
    for subscription in subscriptions:
        graph = session.get(AgateGraph, subscription.graph_id)
        flows.append(
            WebhookFlowOut(
                flow_id=subscription.graph_id,
                flow_name=graph.name if graph else None,
            )
        )
        if subscription.outcomes_json:
            try:
                outcomes = list(json.loads(subscription.outcomes_json))
            except ValueError:
                outcomes = None

    pending = int(
        session.exec(
            select(func.count())
            .select_from(BackfieldWebhookDelivery)
            .where(
                BackfieldWebhookDelivery.endpoint_id == endpoint.id,
                col(BackfieldWebhookDelivery.state).in_(["pending", "delivering"]),
            )
        ).one()
    )
    failed = int(
        session.exec(
            select(func.count())
            .select_from(BackfieldWebhookDelivery)
            .where(
                BackfieldWebhookDelivery.endpoint_id == endpoint.id,
                BackfieldWebhookDelivery.state == DELIVERY_STATE_FAILED,
            )
        ).one()
    )
    return WebhookEndpointOut(
        id=endpoint.id,
        project_id=endpoint.project_id,
        project_name=project.name if project else None,
        project_slug=project.slug if project else None,
        name=endpoint.name,
        destination_host=endpoint.display_host,
        status=endpoint.status,
        secret_version=endpoint.secret_version,
        verified_at=endpoint.verified_at,
        paused_at=endpoint.paused_at,
        pause_reason=endpoint.pause_reason,
        last_success_at=endpoint.last_success_at,
        last_failure_at=endpoint.last_failure_at,
        outcomes=outcomes,  # type: ignore[arg-type]
        flows=sorted(flows, key=lambda flow: (flow.flow_name or "", flow.flow_id)),
        pending_deliveries=pending,
        failed_deliveries=failed,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


# ----- Operations -----


def list_webhook_endpoints(
    session: Session,
    org_id: int,
    *,
    project_id: int | None = None,
) -> list[WebhookEndpointOut]:
    stmt = select(BackfieldWebhookEndpoint).where(
        BackfieldWebhookEndpoint.organization_id == org_id
    )
    if project_id is not None:
        _require_project_in_org(session, org_id, project_id)
        stmt = stmt.where(BackfieldWebhookEndpoint.project_id == project_id)
    endpoints = session.exec(stmt.order_by(col(BackfieldWebhookEndpoint.created_at))).all()
    return [endpoint_to_out(session, endpoint) for endpoint in endpoints]


def create_webhook_endpoint(
    session: Session,
    org_id: int,
    body: WebhookEndpointCreateBody,
    *,
    created_by_user_id: int | None,
) -> WebhookEndpointCreatedOut:
    project = _require_project_in_org(session, org_id, body.project_id)
    _require_flows_in_project(session, int(project.id), body.flow_ids)
    _enforce_endpoint_limit(session, int(project.id))
    url = _validated_url(body.url)

    signing_secret = generate_signing_secret()
    endpoint = BackfieldWebhookEndpoint(
        organization_id=org_id,
        project_id=int(project.id),
        name=body.name.strip(),
        url_encrypted=encrypt_secret(url),
        display_host=display_host_for_url(url),
        signing_secret_encrypted=encrypt_secret(signing_secret),
        status=ENDPOINT_STATUS_PENDING,
        created_by_user_id=created_by_user_id,
    )
    session.add(endpoint)
    session.flush()
    _replace_subscriptions(session, endpoint, body.flow_ids, _outcomes_json(body.outcomes))
    session.commit()
    session.refresh(endpoint)
    return WebhookEndpointCreatedOut(
        endpoint=endpoint_to_out(session, endpoint),
        signing_secret=signing_secret,
    )


def get_webhook_endpoint(session: Session, org_id: int, endpoint_id: str) -> WebhookEndpointOut:
    return endpoint_to_out(session, require_webhook_endpoint(session, org_id, endpoint_id))


def patch_webhook_endpoint(
    session: Session,
    org_id: int,
    endpoint_id: str,
    body: WebhookEndpointPatchBody,
) -> WebhookEndpointOut:
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    now = datetime.now(UTC)

    if body.name is not None:
        endpoint.name = body.name.strip()

    if body.url is not None:
        url = _validated_url(body.url)
        current_url = decrypt_secret(endpoint.url_encrypted)
        if url != current_url:
            # A new destination must prove it can receive signed deliveries.
            endpoint.url_encrypted = encrypt_secret(url)
            endpoint.display_host = display_host_for_url(url)
            endpoint.status = ENDPOINT_STATUS_PENDING
            endpoint.verified_at = None
            endpoint.paused_at = None
            endpoint.pause_reason = None

    if body.flow_ids is not None or body.outcomes is not None or body.clear_outcomes:
        subscriptions = session.exec(
            select(BackfieldWebhookSubscription).where(
                BackfieldWebhookSubscription.endpoint_id == endpoint.id
            )
        ).all()
        current_flow_ids = [subscription.graph_id for subscription in subscriptions]
        flow_ids = body.flow_ids if body.flow_ids is not None else current_flow_ids
        _require_flows_in_project(session, int(endpoint.project_id), flow_ids)
        if body.clear_outcomes:
            outcomes_json = None
        elif body.outcomes is not None:
            outcomes_json = _outcomes_json(body.outcomes)
        else:
            outcomes_json = next(
                (s.outcomes_json for s in subscriptions if s.outcomes_json),
                None,
            )
        _replace_subscriptions(session, endpoint, flow_ids, outcomes_json)

    endpoint.updated_at = now
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return endpoint_to_out(session, endpoint)


def delete_webhook_endpoint(session: Session, org_id: int, endpoint_id: str) -> None:
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    # Delete dependents explicitly rather than relying on DB-level FK cascades
    # (SQLite test databases do not enforce them). Events are retained for the feed.
    delivery_ids = select(BackfieldWebhookDelivery.id).where(
        BackfieldWebhookDelivery.endpoint_id == endpoint.id
    )
    session.exec(
        delete(BackfieldWebhookDeliveryAttempt).where(
            col(BackfieldWebhookDeliveryAttempt.delivery_id).in_(delivery_ids)
        )
    )
    session.exec(
        delete(BackfieldWebhookDelivery).where(
            BackfieldWebhookDelivery.endpoint_id == endpoint.id
        )
    )
    session.exec(
        delete(BackfieldWebhookSubscription).where(
            BackfieldWebhookSubscription.endpoint_id == endpoint.id
        )
    )
    session.delete(endpoint)
    session.commit()


def disable_webhook_endpoint(
    session: Session,
    org_id: int,
    endpoint_id: str,
) -> WebhookEndpointOut:
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    endpoint.status = ENDPOINT_STATUS_DISABLED
    endpoint.updated_at = datetime.now(UTC)
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return endpoint_to_out(session, endpoint)


def activate_webhook_endpoint(
    session: Session,
    org_id: int,
    endpoint_id: str,
) -> WebhookEndpointOut:
    """Resume a paused/disabled endpoint. Future events only; no backlog is replayed."""
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    if endpoint.verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Send a successful test to this destination before turning it on",
        )
    if endpoint.status in (ENDPOINT_STATUS_PAUSED, ENDPOINT_STATUS_DISABLED):
        if endpoint.status == ENDPOINT_STATUS_DISABLED:
            # Re-enabling counts against the per-project active endpoint limit.
            _enforce_endpoint_limit(session, int(endpoint.project_id))
        endpoint.status = ENDPOINT_STATUS_ACTIVE
        endpoint.paused_at = None
        endpoint.pause_reason = None
        endpoint.updated_at = datetime.now(UTC)
        session.add(endpoint)
        session.commit()
        session.refresh(endpoint)
    return endpoint_to_out(session, endpoint)


def rotate_webhook_secret(session: Session, org_id: int, endpoint_id: str) -> WebhookSecretOut:
    """Issue a new signing secret; the endpoint must reverify before delivering again."""
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    signing_secret = generate_signing_secret()
    endpoint.signing_secret_encrypted = encrypt_secret(signing_secret)
    endpoint.secret_version = int(endpoint.secret_version or 1) + 1
    endpoint.status = ENDPOINT_STATUS_PENDING
    endpoint.verified_at = None
    endpoint.paused_at = None
    endpoint.pause_reason = None
    endpoint.updated_at = datetime.now(UTC)
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return WebhookSecretOut(
        signing_secret=signing_secret,
        secret_version=endpoint.secret_version,
        endpoint=endpoint_to_out(session, endpoint),
    )


def list_webhook_deliveries(
    session: Session,
    org_id: int,
    endpoint_id: str,
    *,
    limit: int = 50,
) -> list[WebhookDeliveryOut]:
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    deliveries = session.exec(
        select(BackfieldWebhookDelivery)
        .where(BackfieldWebhookDelivery.endpoint_id == endpoint.id)
        .order_by(col(BackfieldWebhookDelivery.created_at).desc())
        .limit(limit)
    ).all()
    out: list[WebhookDeliveryOut] = []
    for delivery in deliveries:
        event = session.get(BackfieldEvent, delivery.event_id)
        attempts = session.exec(
            select(BackfieldWebhookDeliveryAttempt)
            .where(BackfieldWebhookDeliveryAttempt.delivery_id == delivery.id)
            .order_by(col(BackfieldWebhookDeliveryAttempt.attempt_number))
        ).all()
        out.append(
            WebhookDeliveryOut(
                id=delivery.id,
                event_id=event.event_uuid if event else "",
                event_type=event.event_type if event else "",
                flow_name=event.graph_name if event else None,
                run_id=event.run_id if event else None,
                state=delivery.state,
                attempt_count=delivery.attempt_count,
                next_attempt_at=delivery.next_attempt_at,
                last_status_code=delivery.last_status_code,
                failure_category=delivery.failure_category,
                failure_summary=delivery.failure_summary,
                is_replay=delivery.is_replay,
                is_test=delivery.is_test,
                created_at=delivery.created_at,
                delivered_at=delivery.delivered_at,
                attempts=[
                    WebhookDeliveryAttemptOut(
                        attempt_number=attempt.attempt_number,
                        attempted_at=attempt.attempted_at,
                        status_code=attempt.status_code,
                        failure_category=attempt.failure_category,
                        failure_summary=attempt.failure_summary,
                        duration_ms=attempt.duration_ms,
                    )
                    for attempt in attempts
                ],
            )
        )
    return out


def replay_webhook_delivery(
    session: Session,
    org_id: int,
    endpoint_id: str,
    delivery_id: str,
) -> str:
    """Queue a manual replay as a new delivery of the same event; returns the new ID."""
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    if endpoint.status != ENDPOINT_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Turn this destination on before resending deliveries",
        )
    source = session.get(BackfieldWebhookDelivery, delivery_id)
    if source is None or source.endpoint_id != endpoint.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )
    if source.is_test:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Test deliveries can't be resent; send a new test instead",
        )
    replay = BackfieldWebhookDelivery(
        event_id=source.event_id,
        endpoint_id=endpoint.id,
        state=DELIVERY_STATE_PENDING,
        next_attempt_at=datetime.now(UTC),
        is_replay=True,
    )
    session.add(replay)
    session.commit()
    return replay.id
