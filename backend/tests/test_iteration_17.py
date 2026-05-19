import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""Iteration 17 — Editable Roles & Permissions matrix + custom roles.

Covers:
- PUT/DELETE /api/access/matrix/cell (IT Admin only; validation; effective reflects override).
- POST /api/access/roles + DELETE /api/access/roles/{key} (IT Admin; validation; rebase users).
- GET /api/access/matrix exposes custom_roles, system_roles, valid_levels, and inheritance column.
- PUT /api/access/users/{id}/role accepts custom roles.
- Regression: iter-16 matrix shape, M18 finance access, /access/users.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASSWORD = _DEMO_PWD

EMAILS = {
    "hr_admin": "jessica@solvit.co.ke",
    "line_manager": "manager@solvit.co.ke",
    "finance": "finance@solvit.co.ke",
    "employee": "employee@solvit.co.ke",
    "solver": "solver@solvit.co.ke",
    "executive": "md@solvit.co.ke",
    "it_admin": "itadmin@solvit.co.ke",
    "board": "board@solvit.co.ke",
}


def _login(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sessions():
    return {k: _login(v) for k, v in EMAILS.items()}


# ---- Cleanup any leftover overrides/custom roles from previous runs ----
@pytest.fixture(scope="module", autouse=True)
def _cleanup(sessions):
    it = sessions["it_admin"]
    # Reset M07 employee cell if previously overridden
    it.delete(f"{BASE_URL}/api/access/matrix/cell", json={"module_id": "M07", "role": "employee"})
    # Remove any test custom roles
    for k in ("ops_lead", "qa_lead"):
        it.delete(f"{BASE_URL}/api/access/roles/{k}")
    yield
    it.delete(f"{BASE_URL}/api/access/matrix/cell", json={"module_id": "M07", "role": "employee"})
    for k in ("ops_lead", "qa_lead"):
        it.delete(f"{BASE_URL}/api/access/roles/{k}")


# =========================================================================
# PUT /api/access/matrix/cell
# =========================================================================
class TestMatrixCellUpdate:
    def test_put_cell_as_itadmin_takes_effect(self, sessions):
        r = sessions["it_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "employee", "level": "Read", "scope": "own_record"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["effective"]["level"] == "Read"
        assert d["effective"]["scope"] == "own_record"

        # Verify via /api/access/check/M07 as employee
        chk = sessions["employee"].get(f"{BASE_URL}/api/access/check/M07")
        assert chk.status_code == 200
        access = chk.json()["access"]
        assert access is not None
        assert access["level"] == "Read"
        assert access["scope"] == "own_record"

    def test_put_cell_as_non_itadmin_403(self, sessions):
        r = sessions["hr_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "employee", "level": "Read"},
        )
        assert r.status_code == 403

    def test_put_cell_invalid_module(self, sessions):
        r = sessions["it_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "MXX", "role": "employee", "level": "Read"},
        )
        assert r.status_code == 400

    def test_put_cell_invalid_role(self, sessions):
        r = sessions["it_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "badrole", "level": "Read"},
        )
        assert r.status_code == 400

    def test_put_cell_invalid_level(self, sessions):
        r = sessions["it_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "employee", "level": "God"},
        )
        assert r.status_code == 400


# =========================================================================
# DELETE /api/access/matrix/cell
# =========================================================================
class TestMatrixCellReset:
    def test_delete_cell_reverts_to_seed_default(self, sessions):
        # Ensure an override exists first
        sessions["it_admin"].put(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "employee", "level": "Read", "scope": "own_record"},
        )
        r = sessions["it_admin"].delete(
            f"{BASE_URL}/api/access/matrix/cell",
            json={"module_id": "M07", "role": "employee"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["deleted"] == 1

        # Employee default for M07 is None (no access)
        chk = sessions["employee"].get(f"{BASE_URL}/api/access/check/M07")
        assert chk.status_code == 200
        assert chk.json()["access"] is None


# =========================================================================
# POST /api/access/roles (custom roles)
# =========================================================================
class TestCustomRoleCreate:
    def test_create_role_as_itadmin(self, sessions):
        r = sessions["it_admin"].post(
            f"{BASE_URL}/api/access/roles",
            json={"key": "ops_lead", "label": "Operations Lead",
                  "description": "x", "inherits_from": "line_manager"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == "ops_lead"
        assert d["label"] == "Operations Lead"
        assert d["inherits_from"] == "line_manager"
        assert "_id" not in d

    def test_duplicate_returns_400(self, sessions):
        r = sessions["it_admin"].post(
            f"{BASE_URL}/api/access/roles",
            json={"key": "ops_lead", "label": "x", "inherits_from": "line_manager"},
        )
        assert r.status_code == 400

    def test_invalid_inherits_from_400(self, sessions):
        r = sessions["it_admin"].post(
            f"{BASE_URL}/api/access/roles",
            json={"key": "bogus_inherit", "label": "B", "inherits_from": "no_such_role"},
        )
        assert r.status_code == 400

    def test_non_itadmin_403(self, sessions):
        r = sessions["hr_admin"].post(
            f"{BASE_URL}/api/access/roles",
            json={"key": "should_fail", "label": "x", "inherits_from": "employee"},
        )
        assert r.status_code == 403


# =========================================================================
# GET /api/access/matrix reflects custom role
# =========================================================================
class TestMatrixIncludesCustomRole:
    def test_custom_role_in_matrix(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/access/matrix")
        assert r.status_code == 200
        d = r.json()
        assert "ops_lead" in d["roles_order"]
        assert d["role_labels"]["ops_lead"] == "Operations Lead"
        custom_keys = {c["key"] for c in d["custom_roles"]}
        assert "ops_lead" in custom_keys
        # Inheritance: M01 line_manager -> Manage:own_reports
        m01 = d["matrix"]["M01"]
        assert "ops_lead" in m01
        assert m01["ops_lead"] is not None
        assert m01["ops_lead"]["level"] == m01["line_manager"]["level"]
        # valid_levels and system_roles present
        assert "valid_levels" in d
        assert "system_roles" in d
        assert "employee" in d["system_roles"]


# =========================================================================
# PUT /api/access/users/{id}/role with custom role
# =========================================================================
class TestAssignCustomRole:
    def test_assign_custom_role_to_solver(self, sessions):
        users = sessions["it_admin"].get(f"{BASE_URL}/api/access/users").json()
        solver = next(u for u in users if u["email"] == EMAILS["solver"])
        original = solver["role"]
        try:
            r = sessions["it_admin"].put(
                f"{BASE_URL}/api/access/users/{solver['id']}/role",
                json={"role": "ops_lead"},
            )
            assert r.status_code == 200, r.text
            # Verify persistence
            users2 = sessions["it_admin"].get(f"{BASE_URL}/api/access/users").json()
            updated = next(u for u in users2 if u["id"] == solver["id"])
            assert updated["role"] == "ops_lead"
        finally:
            # If still ops_lead, revert (will be rebased on delete anyway)
            sessions["it_admin"].put(
                f"{BASE_URL}/api/access/users/{solver['id']}/role",
                json={"role": original},
            )


# =========================================================================
# DELETE /api/access/roles/{key}
# =========================================================================
class TestCustomRoleDelete:
    def test_delete_system_role_400(self, sessions):
        r = sessions["it_admin"].delete(f"{BASE_URL}/api/access/roles/employee")
        assert r.status_code == 400

    def test_delete_unknown_404(self, sessions):
        r = sessions["it_admin"].delete(f"{BASE_URL}/api/access/roles/does_not_exist_xyz")
        assert r.status_code == 404

    def test_delete_role_rebases_users(self, sessions):
        # Assign ops_lead to solver first
        users = sessions["it_admin"].get(f"{BASE_URL}/api/access/users").json()
        solver = next(u for u in users if u["email"] == EMAILS["solver"])
        original = solver["role"]
        sessions["it_admin"].put(
            f"{BASE_URL}/api/access/users/{solver['id']}/role",
            json={"role": "ops_lead"},
        )
        # Now delete the role
        r = sessions["it_admin"].delete(f"{BASE_URL}/api/access/roles/ops_lead")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        # User auto-rebased to employee
        users2 = sessions["it_admin"].get(f"{BASE_URL}/api/access/users").json()
        rebased = next(u for u in users2 if u["id"] == solver["id"])
        assert rebased["role"] == "employee"
        # Restore solver to original role
        if original != "employee":
            sessions["it_admin"].put(
                f"{BASE_URL}/api/access/users/{solver['id']}/role",
                json={"role": original},
            )


# =========================================================================
# Regression — iter 16 matrix shape and M18 finance still work
# =========================================================================
class TestIter16Regression:
    def test_matrix_full_payload(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/access/matrix")
        assert r.status_code == 200
        d = r.json()
        for k in ("matrix", "destructive_actions", "module_labels", "role_labels", "roles_order"):
            assert k in d
        assert len(d["matrix"]) == 19
        assert d["matrix"]["M18"]["finance"]["level"] == "Manage"

    def test_users_list(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/access/users")
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 9

    def test_users_list_hradmin_forbidden(self, sessions):
        r = sessions["hr_admin"].get(f"{BASE_URL}/api/access/users")
        assert r.status_code == 403

    def test_m18_finance_check(self, sessions):
        r = sessions["finance"].get(f"{BASE_URL}/api/access/check/M18")
        assert r.status_code == 200
        a = r.json()["access"]
        assert a["level"] == "Manage" and a["scope"] == "own_team"
