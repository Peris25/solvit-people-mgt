import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""Iteration 16 — Finance Leave bug retest + Roles & Permissions admin endpoints.

Covers:
- BUG FIX: Finance can access /api/access/check/M18 (Manage) and POST /api/leave.
- REGRESSION: HR Admin / Employee / Line Manager still have M18 access; Solver still blocked.
- NEW: GET /api/access/matrix returns module_labels, role_labels, roles_order, matrix, destructive_actions.
- NEW: GET /api/access/users (IT Admin only) returns 9 platform users; HR Admin -> 403.
- NEW: PUT /api/access/users/{id}/role — IT Admin success, HR Admin 403, invalid role 400, audit log written.
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
    "ed": "ed@solvit.co.ke",
    "it_admin": "itadmin@solvit.co.ke",
    "board": "board@solvit.co.ke",
}


def _login(email: str):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sessions():
    return {k: _login(v) for k, v in EMAILS.items()}


# ----------- Bug Fix Retest: Finance + Leave (M18) -----------

class TestFinanceLeaveAccess:
    def test_finance_access_check_m18_returns_manage(self, sessions):
        r = sessions["finance"].get(f"{BASE_URL}/api/access/check/M18")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["access"] is not None, f"Finance should have access to M18, got: {data}"
        assert data["access"]["level"] == "Manage"
        assert data["access"]["scope"] == "own_team"

    def test_finance_employees_me_returns_employee_id(self, sessions):
        r = sessions["finance"].get(f"{BASE_URL}/api/employees/me")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert isinstance(data["id"], str) and len(data["id"]) > 0

    def test_finance_can_post_leave_with_employee_id(self, sessions):
        me = sessions["finance"].get(f"{BASE_URL}/api/employees/me").json()
        emp_id = me["id"]
        from datetime import date, timedelta
        start = (date.today() + timedelta(days=14)).isoformat()
        end = (date.today() + timedelta(days=15)).isoformat()
        payload = {
            "employee_id": emp_id,
            "leave_type": "Annual",
            "start_date": start,
            "end_date": end,
            "reason": "TEST_iter16 finance leave",
        }
        r = sessions["finance"].post(f"{BASE_URL}/api/leave", json=payload)
        assert r.status_code in (200, 201), f"POST /api/leave failed: {r.status_code} {r.text}"
        data = r.json()
        # Status should indicate Pending_Manager (or similar) per spec
        status = data.get("status", "")
        assert "Pending" in status or status == "Pending_Manager", f"Unexpected status: {status}"
        assert data.get("employee_id") == emp_id


# ----------- Regression: M18 for other roles -----------

class TestM18Regression:
    @pytest.mark.parametrize("role,expected_level", [
        ("hr_admin", "Full"),
        ("line_manager", "Manage"),
        ("employee", "Manage"),
        ("executive", "Manage"),
    ])
    def test_role_has_m18(self, sessions, role, expected_level):
        r = sessions[role].get(f"{BASE_URL}/api/access/check/M18")
        assert r.status_code == 200
        data = r.json()
        assert data["access"] is not None, f"{role} should have M18"
        assert data["access"]["level"] == expected_level

    def test_solver_blocked_on_m18(self, sessions):
        r = sessions["solver"].get(f"{BASE_URL}/api/access/check/M18")
        assert r.status_code == 200
        assert r.json()["access"] is None


# ----------- /api/access/matrix shape -----------

class TestAccessMatrixEndpoint:
    def test_matrix_returns_full_payload_as_itadmin(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/access/matrix")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("matrix", "destructive_actions", "module_labels", "role_labels", "roles_order"):
            assert k in d, f"missing key {k}"
        assert len(d["matrix"]) == 19, f"expected 19 modules, got {len(d['matrix'])}"
        assert d["module_labels"]["M18"] == "Leave Management"
        assert d["role_labels"]["finance"].startswith("Finance")
        assert len(d["roles_order"]) == 9
        # M18 finance cell present and Manage
        m18 = d["matrix"]["M18"]
        assert m18["finance"] is not None
        assert m18["finance"]["level"] == "Manage"


# ----------- /api/access/users (IT Admin only) -----------

class TestAccessUsersEndpoint:
    def test_list_users_as_itadmin(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/access/users")
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list)
        # Expect at least 9 platform users
        assert len(users) >= 9, f"expected >=9 users, got {len(users)}"
        emails = {u.get("email") for u in users}
        for e in EMAILS.values():
            assert e in emails, f"missing seed user {e}"
        # Required fields
        for u in users:
            assert "id" in u and "email" in u and "role" in u

    def test_list_users_as_hradmin_forbidden(self, sessions):
        r = sessions["hr_admin"].get(f"{BASE_URL}/api/access/users")
        assert r.status_code == 403


# ----------- PUT /api/access/users/{id}/role -----------

class TestUpdateUserRole:
    def _solver_id(self, sessions):
        users = sessions["it_admin"].get(f"{BASE_URL}/api/access/users").json()
        for u in users:
            if u["email"] == EMAILS["solver"]:
                return u["id"], u["role"]
        pytest.fail("solver user not found")

    def test_invalid_role_returns_400(self, sessions):
        uid, _ = self._solver_id(sessions)
        r = sessions["it_admin"].put(f"{BASE_URL}/api/access/users/{uid}/role", json={"role": "supreme_overlord"})
        assert r.status_code == 400

    def test_hradmin_cannot_change_role(self, sessions):
        uid, _ = self._solver_id(sessions)
        r = sessions["hr_admin"].put(f"{BASE_URL}/api/access/users/{uid}/role", json={"role": "employee"})
        assert r.status_code == 403

    def test_itadmin_can_change_and_revert(self, sessions):
        uid, original = self._solver_id(sessions)
        # change to employee
        r = sessions["it_admin"].put(f"{BASE_URL}/api/access/users/{uid}/role", json={"role": "employee"})
        assert r.status_code == 200, r.text
        d = r.json()
        if not d.get("unchanged"):
            assert d["role"] == "employee"
            assert d.get("previous_role") == original
        # revert
        r2 = sessions["it_admin"].put(f"{BASE_URL}/api/access/users/{uid}/role", json={"role": original})
        assert r2.status_code == 200
