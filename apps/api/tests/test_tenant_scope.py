"""Tenant-isolation invariant tests for `scope_notebooks`.

Every notebook query funnels through `scope_notebooks` (see deps.py), so the
WHERE clause it appends *is* the access-control boundary. We assert the SQL
shape directly — DB-free, fast, and it fails loudly if someone loosens the
scoping. The live 404-across-tenants behavior is exercised in the integration
suite; this locks the query that makes it work.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from pynote_api.auth import Principal
from pynote_api.deps import scope_notebooks
from pynote_core.models import Notebook


def _compiled_sql(principal: Principal) -> str:
    stmt = scope_notebooks(select(Notebook), principal)
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


def test_solo_principal_is_restricted_to_own_non_org_notebooks() -> None:
    sql = _compiled_sql(Principal(user_id="alice"))
    # Solo users see ONLY their own rows AND only those not in any org.
    assert "notebook.owner_user_id = 'alice'" in sql
    assert "notebook.org_id IS NULL" in sql
    # The two conditions are ANDed — a solo user must never see org rows.
    assert " AND " in sql.split("WHERE", 1)[1]


def test_org_principal_sees_org_rows_or_own_solo_rows() -> None:
    sql = _compiled_sql(Principal(user_id="bob", org_id="acme"))
    assert "notebook.org_id = 'acme'" in sql
    assert "notebook.owner_user_id = 'bob'" in sql
    # ORed — org membership OR personal ownership, so switching into an org
    # never hides the user's earlier solo work.
    assert " OR " in sql.split("WHERE", 1)[1]


def test_solo_principal_cannot_match_another_solo_users_rows() -> None:
    """Two solo users with NULL org must not collide (None == None is a trap)."""
    alice = _compiled_sql(Principal(user_id="alice"))
    assert "'alice'" in alice
    assert "'bob'" not in alice
