from __future__ import annotations

import base64

from sqlalchemy import text

from .core import Database
from .sql_models import (
    AuditEvent,
    ConsumerReceipt,
    ControlCase,
    ControlCaseTransition,
    ControlEventRow,
    DeadLetterEvent,
    GraphEdge,
    GraphEntity,
    IdempotencyRecord,
    OutboxEvent,
    RegulationDocument,
    TaxFinding,
    TaxRuleRun,
    TaxRunWorkflow,
    TaxTransactionRow,
)


EXPECTED_REVISION = "20260812_0005"
TENANT_TABLES = tuple(model.__tablename__ for model in (
    AuditEvent,
    TaxTransactionRow,
    TaxRuleRun,
    TaxFinding,
    TaxRunWorkflow,
    RegulationDocument,
    ControlEventRow,
    ControlCase,
    ControlCaseTransition,
    GraphEntity,
    GraphEdge,
    IdempotencyRecord,
    OutboxEvent,
    DeadLetterEvent,
    ConsumerReceipt,
))


class PreflightError(RuntimeError):
    pass


def _backup_key(encoded: str) -> None:
    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise PreflightError("backup key must be valid base64") from exc
    if len(key) != 32:
        raise PreflightError("backup key must decode to exactly 32 bytes")


def run_preflight(
    database_url: str,
    *,
    issuer: str,
    audience: str,
    jwks_url: str,
    backup_key_base64: str,
    allow_dev_tokens: bool = False,
) -> dict:
    if not database_url.startswith("postgresql+psycopg://"):
        raise PreflightError("production database must use postgresql+psycopg")
    if allow_dev_tokens:
        raise PreflightError("development token endpoint must be disabled")
    if not issuer.startswith("https://") or not audience or not jwks_url.startswith("https://"):
        raise PreflightError("production OIDC requires HTTPS issuer/JWKS and audience")
    _backup_key(backup_key_base64)

    database = Database(database_url, create_schema=False)
    try:
        with database.connect() as connection:
            role = connection.execute(text(
                "SELECT current_user AS name, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )).mappings().one()
            if role["rolsuper"]:
                raise PreflightError("request database role must not be superuser")
            if role["rolbypassrls"]:
                raise PreflightError("request database role must be NOBYPASSRLS")
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            if revision != EXPECTED_REVISION:
                raise PreflightError(f"database schema must be at revision {EXPECTED_REVISION}")
            rows = connection.execute(text(
                "SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, "
                "c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            )).mappings()
            tables = {row["relname"]: row for row in rows}
            missing = sorted(set(TENANT_TABLES) - set(tables))
            if missing:
                raise PreflightError(f"missing tenant tables: {', '.join(missing)}")
            if any(tables[name]["owner"] == role["name"] for name in TENANT_TABLES):
                raise PreflightError("request database role must not own tenant tables")
            unprotected = sorted(
                name for name in TENANT_TABLES
                if not tables[name]["relrowsecurity"] or not tables[name]["relforcerowsecurity"]
            )
            if unprotected:
                raise PreflightError(f"tenant tables must enforce RLS: {', '.join(unprotected)}")
    finally:
        database.dispose()

    return {
        "valid": True,
        "database": {
            "dialect": "postgresql",
            "user": role["name"],
            "superuser": False,
            "bypass_rls": False,
            "owns_tenant_tables": False,
            "forced_rls_tables": len(TENANT_TABLES),
        },
        "schema_revision": revision,
        "auth_mode": "oidc",
        "backup_key": "configured-32-bytes",
    }
