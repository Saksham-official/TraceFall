"""Request dependencies: session, authentication, and role checks."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Forbidden, NotFound, Unauthenticated
from app.core.ratelimit import enforce_user_limit
from app.core.security import decode_token
from app.db.models.case import Case, CaseAssignment
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.db.session import SessionFactory

bearer = HTTPBearer(auto_error=False)

# Roles that may read any case. Everyone else sees only owned or assigned cases.
_GLOBAL_READERS = {UserRole.ADMIN, UserRole.ANALYST}


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: SessionDep,
) -> User:
    if credentials is None:
        raise Unauthenticated()
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Token is invalid or has expired") from exc

    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthenticated("Account is inactive or no longer exists")
    # The per-user budget is applied here rather than in middleware, which runs before
    # the token has been decoded and so cannot know who is calling.
    await enforce_user_limit(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden(f"This action requires one of: {', '.join(roles)}")
        return user

    return dependency


async def get_accessible_case(case_id: uuid.UUID, user: User, session: AsyncSession) -> Case:
    """Case isolation, enforced at the query layer (NFR-08).

    Raises NotFound — never Forbidden — for a case the user may not see.
    """
    case = await session.get(Case, case_id)
    if case is None:
        raise NotFound("Case not found")
    if user.role in _GLOBAL_READERS or case.owner_id == user.id:
        return case

    assigned = await session.scalar(
        select(CaseAssignment.id).where(
            CaseAssignment.case_id == case_id, CaseAssignment.user_id == user.id
        )
    )
    if assigned is None:
        raise NotFound("Case not found")
    return case


def visible_cases[S: Select[Any]](stmt: S, user: User) -> S:
    """Narrow a query to the cases this user may see. Case isolation at the query layer.

    Admins and analysts read globally — an I4C analyst correlating across a department's
    reports is the reason the role exists. Everyone else sees what they own or are
    assigned. Shared so that one policy governs every query, rather than each caller
    reimplementing it and one of them getting it wrong.
    """
    if user.role in _GLOBAL_READERS:
        return stmt
    return stmt.outerjoin(CaseAssignment, CaseAssignment.case_id == Case.id).where(
        or_(Case.owner_id == user.id, CaseAssignment.user_id == user.id)
    )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")
