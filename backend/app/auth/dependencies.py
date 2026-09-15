"""The app-facing auth seam.

Every route depends on `get_current_user`, which returns the minimal
`CurrentUser` the rest of the app needs: who is asking. Retrieval, documents
and threads all filter on that user's id, so one user can never see another
user's documents or answers.

This indirection is deliberate: to put the starter behind an external
identity provider (Keycloak, Authentik, WorkOS, Auth0 or any OIDC issuer),
reimplement ONLY this function to verify that provider's token. See
docs/setup-auth.md.
"""

import uuid

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from app.auth.backend import fastapi_users
from app.db.models import User

current_user_optional = fastapi_users.current_user(active=True, optional=True)


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str


def get_current_user(cookie_user: User | None = Depends(current_user_optional)) -> CurrentUser:
    if cookie_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return CurrentUser(id=cookie_user.id, email=cookie_user.email)
