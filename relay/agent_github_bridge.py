"""GitHub Actions OIDC exchange for the temporary binary project bridge.

Only the repository's trusted transfer workflow can obtain an agent_controller
credential. No long-lived GitHub or Neon secret is stored in GitHub Actions.
"""
from __future__ import annotations

import json
import os
import secrets
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from command_center import authenticate_device, digest_secret, get_pool

router = APIRouter(prefix="/v1/agent-bridge/github", tags=["agent-binary-bridge"])

OIDC_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_AUDIENCE = "godot-relay-agent-bridge"
OIDC_JWKS_URL = f"{OIDC_ISSUER}/.well-known/jwks"
TRUSTED_REPOSITORY = "decuvilan-lgtm/Godot-web-ia-integrada"
TRUSTED_REPOSITORY_ID = "1448988160"
TRUSTED_OWNER_ID = "345667326"
TRUSTED_ACTOR_ID = "345667326"
TRUSTED_WORKFLOW = ".github/workflows/agent-binary-bridge.yml"
AGENT_DEVICE_INSTALLATION = "github-actions:1448988160:agent-binary-bridge"
AGENT_DEVICE_LABEL = "GitHub Actions binary bridge"

_jwks_client = PyJWKClient(OIDC_JWKS_URL, cache_jwk_set=True, lifespan=3600)


def validate_github_claims(claims: dict[str, Any]) -> None:
    """Enforce repository, actor, workflow and ref boundaries after JWT validation."""
    if claims.get("iss") != OIDC_ISSUER:
        raise HTTPException(status_code=403, detail="Untrusted GitHub OIDC issuer")
    if claims.get("repository") != TRUSTED_REPOSITORY:
        raise HTTPException(status_code=403, detail="GitHub repository is not authorized")
    if str(claims.get("repository_id", "")) != TRUSTED_REPOSITORY_ID:
        raise HTTPException(status_code=403, detail="GitHub repository ID is not authorized")
    if str(claims.get("repository_owner_id", "")) != TRUSTED_OWNER_ID:
        raise HTTPException(status_code=403, detail="GitHub repository owner is not authorized")
    if str(claims.get("actor_id", "")) != TRUSTED_ACTOR_ID:
        raise HTTPException(status_code=403, detail="GitHub actor is not authorized")
    if claims.get("event_name") != "push":
        raise HTTPException(status_code=403, detail="Only trusted push events are authorized")
    ref = claims.get("ref", "")
    if not isinstance(ref, str) or not ref.startswith("refs/heads/agent-transfer/"):
        raise HTTPException(status_code=403, detail="Git ref is outside the agent-transfer namespace")
    workflow_ref = claims.get("workflow_ref", "")
    expected_prefix = f"{TRUSTED_REPOSITORY}/{TRUSTED_WORKFLOW}@refs/heads/agent-transfer/"
    if not isinstance(workflow_ref, str) or not workflow_ref.startswith(expected_prefix):
        raise HTTPException(status_code=403, detail="GitHub workflow is not authorized")
    if not str(claims.get("run_id", "")).isdigit() or not str(claims.get("run_attempt", "")).isdigit():
        raise HTTPException(status_code=403, detail="GitHub workflow run identity is incomplete")


async def decode_github_oidc(token: str) -> dict[str, Any]:
    try:
        signing_key = await run_in_threadpool(_jwks_client.get_signing_key_from_jwt, token)
        claims = await run_in_threadpool(
            jwt.decode,
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="GitHub OIDC token is invalid or expired") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GitHub OIDC verification is temporarily unavailable") from exc
    validate_github_claims(claims)
    return claims


def bearer_value(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="GitHub OIDC bearer token required")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token or len(token) > 16384:
        raise HTTPException(status_code=401, detail="GitHub OIDC bearer token required")
    return token


@router.post("/exchange", status_code=201)
async def exchange_github_oidc(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Exchange a short-lived GitHub OIDC assertion for a rotating agent device token."""
    claims = await decode_github_oidc(bearer_value(authorization))
    pool = await get_pool(request)
    workspace_slug = os.environ.get("AGENT_GITHUB_WORKSPACE_SLUG", "default").strip() or "default"
    workspace_id = await pool.fetchval(
        "SELECT id FROM command_center.workspaces WHERE slug=$1",
        workspace_slug,
    )
    if workspace_id is None:
        raise HTTPException(status_code=503, detail="Configured agent workspace does not exist")

    credential = secrets.token_urlsafe(48)
    device_id = await pool.fetchval(
        """INSERT INTO command_center.devices
           (workspace_id, device_kind, label, installation_id, token_hash, last_seen_at, revoked_at)
           VALUES ($1,'agent_controller',$2,$3,$4,now(),NULL)
           ON CONFLICT (workspace_id, installation_id)
           DO UPDATE SET device_kind='agent_controller',
                         label=EXCLUDED.label,
                         token_hash=EXCLUDED.token_hash,
                         last_seen_at=now(),
                         revoked_at=NULL
           RETURNING id""",
        workspace_id,
        AGENT_DEVICE_LABEL,
        AGENT_DEVICE_INSTALLATION,
        digest_secret(credential),
    )
    await pool.execute(
        """INSERT INTO command_center.events
           (workspace_id, actor_device_id, event_type, payload)
           VALUES ($1,$2,'agent.github_actions_authenticated',$3::jsonb)""",
        workspace_id,
        device_id,
        json.dumps({
            "repository": TRUSTED_REPOSITORY,
            "ref": claims["ref"],
            "run_id": str(claims["run_id"]),
            "run_attempt": str(claims["run_attempt"]),
        }),
    )
    return {
        "device_id": str(device_id),
        "device_kind": "agent_controller",
        "token_type": "Bearer",
        "access_token": credential,
        "expires_in_seconds": 1800,
    }


@router.post("/revoke", status_code=200)
async def revoke_github_agent(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Revoke the temporary bridge credential at the end of a workflow run."""
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] != "agent_controller" or identity["label"] != AGENT_DEVICE_LABEL:
        raise HTTPException(status_code=403, detail="Only the GitHub Actions bridge device can revoke itself")
    pool = await get_pool(request)
    await pool.execute(
        "UPDATE command_center.devices SET revoked_at=now() WHERE id=$1 AND revoked_at IS NULL",
        identity["id"],
    )
    return {"revoked": True}
