"""fastapi-users UserManager: user lifecycle hooks and token secrets.

The starter ships registration, login and logout. Password reset and email
verification need an email provider, so their routes are not mounted; see
docs/setup-auth.md for adding them.
"""

import uuid

from fastapi import Depends
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase

from app.auth.db import get_user_db
from app.config import settings
from app.db.models import User
from app.logging import get_logger

log = get_logger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.auth_secret
    verification_token_secret = settings.auth_secret

    async def on_after_register(self, user: User, request=None) -> None:
        log.info("user.registered", user_id=str(user.id))


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)
