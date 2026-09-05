"""Every route is reachable, authenticated, and covered by a test.

Two things this catches that per-endpoint tests do not: a route added without any test at
all, and a route added without authentication. Both are easy to do and neither shows up
until someone goes looking.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.main import app

TESTS = Path(__file__).parent

# Documented as open by design: health is polled by orchestration, and the auth routes are
# how a caller gets a token in the first place.
PUBLIC = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
}


def routes() -> list[tuple[str, str]]:
    """Every documented operation, from the OpenAPI schema.

    Read from the schema rather than walking `app.routes`: included routers nest rather
    than flatten, so the route list is three entries long and misses everything. The
    schema is also the thing a client is written against, which makes it the right
    definition of "the contract" for this test.
    """
    schema = app.openapi()
    return sorted(
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1")
        for method in operations
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    )


def _fill(path: str, method: str) -> str:
    """Substitute every path parameter using its declared type."""
    operation = app.openapi()["paths"][path][method.lower()]
    filled = path
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "path":
            continue
        schema = parameter.get("schema", {})
        if schema.get("format") == "uuid" or schema.get("type") == "string":
            value = "00000000-0000-0000-0000-000000000000"
        else:
            value = "1"
        filled = filled.replace(f"{{{parameter['name']}}}", value)
    return filled


def test_every_route_is_exercised_by_a_test() -> None:
    """A route with no test is a route nobody has checked the shape of."""
    suite = "\n".join(
        path.read_text() for path in TESTS.glob("test_*.py") if path.name != Path(__file__).name
    )

    untested = [
        (method, path)
        for method, path in routes()
        # The literal path prefix appears in the test that calls it; parameters differ.
        if path.split("{")[0].replace("/api/v1", "") not in suite
    ]

    assert untested == [], f"routes with no test: {untested}"


@pytest.mark.parametrize(("method", "path"), routes())
async def test_every_route_requires_authentication(
    client: AsyncClient, method: str, path: str
) -> None:
    """Anything that is not deliberately public must reject an anonymous caller."""
    if path in PUBLIC:
        return

    # Path parameters are filled with values that are well-formed but match nothing, so a
    # 404 would mean the route ran — which is exactly what must not happen. Types come
    # from the schema, so a new route needs no change here.
    concrete = _fill(path, method)
    assert "{" not in concrete, f"unfilled path parameter in {path}"

    response = await client.request(method, concrete, json={})

    assert response.status_code in (401, 403), (
        f"{method} {path} returned {response.status_code} to an anonymous caller"
    )


def test_the_public_routes_are_the_documented_ones() -> None:
    """Adding to this set is a security decision, so it is asserted rather than assumed."""
    assert {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    } == PUBLIC
    assert routes(), "the contract must not be empty"
