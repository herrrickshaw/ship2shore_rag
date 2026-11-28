"""CORS must not be open to every website unless that is asked for."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402

DEMO = "https://ship2shore-ops-demo.lovable.app"


def preflight(origin):
    headers = {"Origin": origin, "Access-Control-Request-Method": "GET"}
    return TestClient(api.app).options("/vessels", headers=headers)


@pytest.mark.parametrize("raw", [None, "", " , "])
def test_unset_or_blank_setting_uses_the_defaults(raw):
    assert api.cors_origins(raw) == api.DEFAULT_CORS_ORIGINS.split(",")
    assert "*" not in api.cors_origins(raw)


def test_setting_is_split_and_trailing_slashes_dropped():
    assert api.cors_origins(" https://a.example/ ,https://b.example") == [
        "https://a.example", "https://b.example",
    ]


def test_demo_frontend_is_allowed_and_other_sites_are_not():
    assert preflight(DEMO).headers.get("access-control-allow-origin") == DEMO
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers
