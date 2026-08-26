"""Minimal IAM for the operations module: identity + role-based authorization,
scoped to what a CLI tool actually needs — no passwords, no sessions, no web
server. "Logged in" means the current user's name is passed via --user or the
SHIP2SHORE_USER env var and looked up in the `users` table; authorization is
then a role check before a sensitive command runs. See README "Operations
module — IAM" for why this is the right scope here, not full web auth.
"""
import os

ROLES = ("master", "chief_engineer", "officer", "deck_crew", "engine_crew", "shore_staff")

# action -> roles allowed to perform it. Anything not listed here is
# unrestricted (e.g. all the "list"/read commands).
PERMISSIONS = {
    "log:captain": {"master"},
    "log:engine": {"master", "chief_engineer", "engine_crew"},
    "log:deck": {"master", "officer", "deck_crew"},
    "crew:signon": {"master", "shore_staff"},
    "crew:signoff": {"master", "shore_staff"},
    "vessel:add": {"master", "shore_staff"},
    "equipment:add": {"master", "chief_engineer"},
    "parts:add": {"master", "chief_engineer"},
    "maintenance:add": {"master", "chief_engineer", "engine_crew"},
    "fuel:add": {"master", "chief_engineer"},
    "procurement:add": {"master", "chief_engineer", "shore_staff"},
    "procurement:approve": {"master", "shore_staff"},
    "drydock:add": {"master", "shore_staff"},
    "safety:close": {"master", "shore_staff"},
    # Deliberately NOT in this table: "safety:report". Near-miss/incident
    # reporting is unrestricted on purpose — a no-blame reporting culture
    # where anyone aboard can report is standard safety-management practice,
    # not an oversight. See db/ops_schema.sql's comment on safety_incidents.
}


class AuthError(Exception):
    pass


def current_user_name(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("SHIP2SHORE_USER")


def require_role(user: dict | None, action: str) -> None:
    """`user` is a row dict from users (name, role) or None. Raises AuthError
    if the action is restricted and the user isn't allowed to perform it."""
    allowed = PERMISSIONS.get(action)
    if allowed is None:
        return  # unrestricted action
    if user is None:
        raise AuthError(
            f"{action!r} requires a role in {sorted(allowed)} — pass --user <name> "
            "(or set SHIP2SHORE_USER) for a user registered via `cli.py user add`"
        )
    if user["role"] not in allowed:
        raise AuthError(f"{action!r} requires a role in {sorted(allowed)}, but {user['name']!r} is {user['role']!r}")
