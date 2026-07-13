from datetime import datetime
from typing import Annotated

from fastapi import Header

from futbot_common.errors import AuthError


def optional_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str | None:
    return x_user_id


def require_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    if not x_user_id:
        raise AuthError("LOGIN_REQUIRED", "Authentication required.", 403)
    return x_user_id


def assert_chat_access(chat_user_id: str | None, request_user_id: str | None) -> None:
    if chat_user_id:
        if chat_user_id != request_user_id:
            raise AuthError("FORBIDDEN", "You do not have access to this chat.", 403)
    elif request_user_id:
        raise AuthError("FORBIDDEN", "You do not have access to this chat.", 403)
