from copy import copy
from typing import Optional

from fastapi import Depends, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.api.api_v1 import api_router_v1
from app.database import get_db
from app.models import User
from app.util.rest_util import get_failed_response
from app.util.util import get_user_tokens
import hashlib


class LoginRequest(BaseModel):
    email: Optional[str] = None
    user_name: Optional[str] = None
    password: str
    is_web: bool


@api_router_v1.post("/login", status_code=200)
async def login_user(
    login_request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = login_request.email
    user_name = login_request.user_name
    password = login_request.password
    is_web = login_request.is_web
    if password is None or (email is None and user_name is None):
        return get_failed_response("Invalid request", response)
    if user_name is None:
        # login with email
        email_hash = hashlib.sha512(email.lower().encode("utf-8")).hexdigest()
        statement = (
            select(User)
            .where(User.origin == 0)
            .where(User.email_hash == email_hash)
            .options(selectinload(User.friends))
        )
        results = await db.execute(statement)
        result_user = results.first()
    elif email is None:
        statement = (
            select(User)
            .where(User.origin == 0)
            .where(func.lower(User.username) == user_name.lower())
            .options(selectinload(User.friends))
        )
        results = await db.execute(statement)
        result_user = results.first()
    else:
        return get_failed_response("Invalid request", response)

    if not result_user:
        return get_failed_response("user name or email not found", response)

    user: User = result_user.User
    return_user = copy(user.serialize)

    if not user.verify_password(password):
        return get_failed_response("password not correct", response)

    # If the platform is 3 we don't need to check anything anymore.
    platform_achievement = False

    if user.platform != 3:
        if is_web:
            platform_value = user.logged_in_web()
            if platform_value > 0:
                db.add(user)
            if platform_value == 2:
                platform_achievement = True
        elif not is_web:
            platform_value = user.logged_in_mobile()
            if platform_value > 0:
                db.add(user)
            if platform_value == 2:
                platform_achievement = True
    # Valid login, we refresh the token for this user.
    user_token = get_user_tokens(user)
    db.add(user_token)
    await db.commit()

    # We don't refresh the user object because we know all we want to know
    login_response = {
        "result": True,
        "message": "user logged in successfully.",
        "access_token": user_token.access_token,
        "refresh_token": user_token.refresh_token,
        "user": return_user,
        "platform_achievement": platform_achievement
    }

    return login_response
