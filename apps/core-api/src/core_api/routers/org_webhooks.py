"""Organization webhook endpoint management (org admin only)."""

from __future__ import annotations

from backfield_db import BackfieldProject
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session
from core_api.run_enqueue import enqueue_worker_task
from core_api.webhook_verification import WebhookTestResultOut, send_webhook_verification_test
from core_api.webhooks_admin import (
    WebhookDeliveryOut,
    WebhookEndpointCreateBody,
    WebhookEndpointCreatedOut,
    WebhookEndpointOut,
    WebhookEndpointPatchBody,
    WebhookSecretOut,
    activate_webhook_endpoint,
    create_webhook_endpoint,
    delete_webhook_endpoint,
    disable_webhook_endpoint,
    endpoint_to_out,
    get_webhook_endpoint,
    list_webhook_deliveries,
    list_webhook_endpoints,
    patch_webhook_endpoint,
    replay_webhook_delivery,
    require_webhook_endpoint,
    rotate_webhook_secret,
)

router = APIRouter(prefix="/organizations", tags=["admin-webhooks"])


class WebhookTestResponse(BaseModel):
    result: WebhookTestResultOut
    endpoint: WebhookEndpointOut


class WebhookReplayOut(BaseModel):
    delivery_id: str


@router.get("/{org_id}/webhook-endpoints", response_model=list[WebhookEndpointOut])
def get_organization_webhook_endpoints(
    org_id: int,
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[WebhookEndpointOut]:
    require_org_admin(session, auth, org_id)
    return list_webhook_endpoints(session, org_id, project_id=project_id)


@router.post("/{org_id}/webhook-endpoints", response_model=WebhookEndpointCreatedOut)
def post_organization_webhook_endpoint(
    org_id: int,
    body: WebhookEndpointCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookEndpointCreatedOut:
    """Create a pending endpoint; the signing secret is returned exactly once."""
    require_org_admin(session, auth, org_id)
    user_id = auth.get("user_id")
    return create_webhook_endpoint(
        session,
        org_id,
        body,
        created_by_user_id=int(user_id) if user_id is not None else None,
    )


@router.get("/{org_id}/webhook-endpoints/{endpoint_id}", response_model=WebhookEndpointOut)
def get_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookEndpointOut:
    require_org_admin(session, auth, org_id)
    return get_webhook_endpoint(session, org_id, endpoint_id)


@router.patch("/{org_id}/webhook-endpoints/{endpoint_id}", response_model=WebhookEndpointOut)
def patch_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    body: WebhookEndpointPatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookEndpointOut:
    """Update name/URL/flows/outcomes; changing the URL requires reverification."""
    require_org_admin(session, auth, org_id)
    return patch_webhook_endpoint(session, org_id, endpoint_id, body)


@router.delete("/{org_id}/webhook-endpoints/{endpoint_id}", status_code=204)
def delete_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> None:
    require_org_admin(session, auth, org_id)
    delete_webhook_endpoint(session, org_id, endpoint_id)


@router.post(
    "/{org_id}/webhook-endpoints/{endpoint_id}/disable",
    response_model=WebhookEndpointOut,
)
def disable_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookEndpointOut:
    require_org_admin(session, auth, org_id)
    return disable_webhook_endpoint(session, org_id, endpoint_id)


@router.post(
    "/{org_id}/webhook-endpoints/{endpoint_id}/activate",
    response_model=WebhookEndpointOut,
)
def activate_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookEndpointOut:
    """Resume a paused or disabled endpoint (future events only, no backlog)."""
    require_org_admin(session, auth, org_id)
    return activate_webhook_endpoint(session, org_id, endpoint_id)


@router.post(
    "/{org_id}/webhook-endpoints/{endpoint_id}/rotate-secret",
    response_model=WebhookSecretOut,
)
def rotate_organization_webhook_secret(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookSecretOut:
    """Issue a new signing secret (shown once); requires a fresh successful test."""
    require_org_admin(session, auth, org_id)
    return rotate_webhook_secret(session, org_id, endpoint_id)


@router.post(
    "/{org_id}/webhook-endpoints/{endpoint_id}/test",
    response_model=WebhookTestResponse,
)
def test_organization_webhook_endpoint(
    org_id: int,
    endpoint_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookTestResponse:
    """Send a signed test delivery now; a 2xx response activates a pending endpoint."""
    require_org_admin(session, auth, org_id)
    endpoint = require_webhook_endpoint(session, org_id, endpoint_id)
    project = session.get(BackfieldProject, endpoint.project_id)
    result = send_webhook_verification_test(session, endpoint=endpoint, project=project)
    session.refresh(endpoint)
    return WebhookTestResponse(result=result, endpoint=endpoint_to_out(session, endpoint))


@router.get(
    "/{org_id}/webhook-endpoints/{endpoint_id}/deliveries",
    response_model=list[WebhookDeliveryOut],
)
def get_organization_webhook_deliveries(
    org_id: int,
    endpoint_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[WebhookDeliveryOut]:
    require_org_admin(session, auth, org_id)
    return list_webhook_deliveries(session, org_id, endpoint_id, limit=limit)


@router.post(
    "/{org_id}/webhook-endpoints/{endpoint_id}/deliveries/{delivery_id}/replay",
    response_model=WebhookReplayOut,
)
def replay_organization_webhook_delivery(
    org_id: int,
    endpoint_id: str,
    delivery_id: str,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WebhookReplayOut:
    """Queue one manual redelivery of an event with a new delivery ID."""
    require_org_admin(session, auth, org_id)
    new_delivery_id = replay_webhook_delivery(session, org_id, endpoint_id, delivery_id)
    try:
        enqueue_worker_task("worker.tasks.dispatch_webhook_deliveries", [])
    except Exception:
        # The scheduled recovery sweep remains authoritative.
        pass
    return WebhookReplayOut(delivery_id=new_delivery_id)
