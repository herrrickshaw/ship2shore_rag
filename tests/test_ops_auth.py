import pytest

from ops.auth import AuthError, require_role


def test_unrestricted_action_allows_anyone():
    require_role(None, "some:unlisted-action")  # no exception


def test_restricted_action_denies_no_user():
    with pytest.raises(AuthError):
        require_role(None, "log:captain")


def test_restricted_action_denies_wrong_role():
    with pytest.raises(AuthError):
        require_role({"name": "Deck Hand", "role": "deck_crew"}, "log:captain")


def test_restricted_action_allows_correct_role():
    require_role({"name": "Captain Ahab", "role": "master"}, "log:captain")  # no exception


def test_engine_log_allows_chief_engineer_and_engine_crew_and_master():
    for role in ("chief_engineer", "engine_crew", "master"):
        require_role({"name": "x", "role": role}, "log:engine")


def test_engine_log_denies_deck_crew():
    with pytest.raises(AuthError):
        require_role({"name": "x", "role": "deck_crew"}, "log:engine")


def test_safety_report_is_unrestricted_for_any_role():
    # Deliberate design choice: no-blame safety reporting is open to everyone.
    for role in ("deck_crew", "engine_crew", "officer", "chief_engineer", "master", "shore_staff"):
        require_role({"name": "x", "role": role}, "safety:report")
    require_role(None, "safety:report")  # even with no user set


def test_procurement_approve_denies_chief_engineer():
    with pytest.raises(AuthError):
        require_role({"name": "x", "role": "chief_engineer"}, "procurement:approve")


def test_procurement_approve_allows_shore_staff_and_master():
    for role in ("shore_staff", "master"):
        require_role({"name": "x", "role": role}, "procurement:approve")


def test_drydock_add_denies_chief_engineer():
    with pytest.raises(AuthError):
        require_role({"name": "x", "role": "chief_engineer"}, "drydock:add")
