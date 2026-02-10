from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request

from ..config import Settings
from ..db import ensure_user, try_decrement_credits


@dataclass(frozen=True)
class UserContext:
    user_id: UUID
    email: str


def user_context_dependency(settings: Settings):
    async def resolve_user(request: Request) -> UserContext:
        email = request.headers.get("x-user-email") or "anonymous@local"
        pool = request.app.state.db
        user_id = await ensure_user(pool, email, settings.free_tier_credits)
        if settings.enable_billing:
            ok = await try_decrement_credits(pool, user_id)
            if not ok:
                raise HTTPException(status_code=402, detail="Insufficient credits")
        return UserContext(user_id=user_id, email=email)

    return resolve_user
