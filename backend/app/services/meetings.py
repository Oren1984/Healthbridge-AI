"""LiveKit access tokens and server reachability.

Tokens are short-lived, bound to one room and one identity, and are issued only after the
consultation authorization checks in the API layer. Recording/egress permissions are never granted.
"""
from datetime import timedelta

import httpx
from livekit import api

from app.config import get_settings


def create_join_token(room: str, identity: str, name: str, can_publish: bool = True) -> str:
    s = get_settings()
    if not s.livekit_api_key or len(s.livekit_api_secret) < 32:
        raise RuntimeError("LiveKit is not configured")
    grants = api.VideoGrants(room_join=True, room=room, can_publish=can_publish, can_subscribe=True,
                             can_publish_data=True, room_record=False, room_admin=False)
    return (api.AccessToken(s.livekit_api_key, s.livekit_api_secret)
            .with_identity(identity).with_name(name).with_grants(grants)
            .with_ttl(timedelta(seconds=s.livekit_token_ttl_seconds)).to_jwt())


def livekit_reachable() -> bool:
    try:
        r = httpx.get(get_settings().livekit_internal_url, timeout=2.0)
        return r.status_code < 500
    except httpx.HTTPError:
        return False
