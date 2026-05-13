"""
Iteration 14 — Line Manager dashboard widget + strict line_manager scope.

Covers:
- GET /api/dashboard/line-manager: data shape + RBAC (manager 200, solver 403,
  hr_admin/it_admin 200).
- /api/employees scope: line_manager sees only self + direct reports.
- /api/leave scope: line_manager sees only own + direct reports' leave requests.
- Regression: HR admin / finance / employee scopes unchanged.
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PWD = "Solvit@2026"


def login(email):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


# ---------- /api/dashboard/line-manager widget ----------
class TestLineManagerWidget:
    def test_manager_widget_shape_and_team(self):
        s = login("manager@solvit.co.ke")
        r = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()

        # Top-level required fields
        for key in (
            "manager_employee_id", "team", "team_size", "pending_leave",
            "flight_risk_summary", "open_reviews", "my_open_tasks",
        ):
            assert key in data, f"missing {key} in widget response: {data.keys()}"

        # Team_size >= 2 and David's reports present
        assert data["team_size"] >= 2, f"expected team_size>=2 for David, got {data['team_size']}"
        names = {t.get("full_name") for t in data["team"]}
        assert "James Kamau" in names, f"James Kamau not in team {names}"
        assert "Robert Kiprotich" in names, f"Robert Kiprotich not in team {names}"

        # Flight risk summary has all 4 buckets
        fr = data["flight_risk_summary"]
        for k in ("Critical", "High", "Elevated", "Healthy"):
            assert k in fr, f"flight_risk_summary missing {k}: {fr}"
            assert isinstance(fr[k], int)

        # Each team row has the documented signal fields
        sample = data["team"][0]
        for key in (
            "id", "full_name", "lifecycle_state", "flight_risk_level",
            "pending_leave", "open_reviews", "days_since_last_review",
            "last_performance_score",
        ):
            assert key in sample, f"team row missing {key}: {sample.keys()}"

        # pending_leave is a number type
        assert isinstance(data["pending_leave"], int)
        assert isinstance(data["open_reviews"], int)
        assert isinstance(data["my_open_tasks"], int)

    def test_solver_widget_forbidden(self):
        s = login("solver@solvit.co.ke")
        r = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20)
        assert r.status_code == 403, f"solver should be 403 got {r.status_code}: {r.text}"

    def test_hr_admin_widget_ok(self):
        s = login("jessica@solvit.co.ke")
        r = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20)
        assert r.status_code == 200, r.text
        # hr_admin record exists -> should have manager_employee_id
        data = r.json()
        assert "team" in data

    def test_it_admin_widget_ok(self):
        s = login("itadmin@solvit.co.ke")
        r = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20)
        assert r.status_code == 200, r.text


# ---------- /api/employees scope ----------
class TestEmployeesScope:
    def test_manager_sees_only_self_plus_direct_reports(self):
        s = login("manager@solvit.co.ke")
        r = s.get(f"{BASE}/api/employees", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        # Should be a small set (self + 2 reports == 3) — strictly NO Sarah/Jessica/MD/etc.
        names = {e.get("full_name") for e in rows}
        assert "David Ochieng" in names, f"manager must see self: {names}"
        assert "James Kamau" in names, f"manager must see James: {names}"
        assert "Robert Kiprotich" in names, f"manager must see Robert: {names}"
        forbidden = {"Sarah Njoroge", "Jessica Mwangi", "Michael Omondi", "Esther Wanjala", "Isaac Karanja"}
        leaked = forbidden & names
        assert not leaked, f"manager LEAKED non-team rows: {leaked} | all={names}"
        assert len(rows) == 3, f"expected exactly 3 rows (self+2 reports), got {len(rows)}: {names}"

    def test_hr_admin_sees_full_org(self):
        s = login("jessica@solvit.co.ke")
        r = s.get(f"{BASE}/api/employees", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        # HR Admin should see many rows (full org minus board-only MD/ED hides)
        assert len(rows) >= 10, f"hr_admin expected full org list, got {len(rows)}"
        names = {e.get("full_name") for e in rows}
        # Sanity: HR can see Sarah, David, themselves
        assert "Sarah Njoroge" in names
        assert "David Ochieng" in names

    def test_finance_sees_org(self):
        s = login("finance@solvit.co.ke")
        r = s.get(f"{BASE}/api/employees", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) >= 5, f"finance expected org-wide list, got {len(rows)}"

    def test_employee_sees_only_own_row(self):
        s = login("employee@solvit.co.ke")
        r = s.get(f"{BASE}/api/employees", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1, f"employee should see only own row, got {len(rows)}: {[e.get('full_name') for e in rows]}"
        assert rows[0].get("full_name") == "James Kamau"


# ---------- /api/leave scope ----------
class TestLeaveScope:
    def test_manager_leave_scope(self):
        s = login("manager@solvit.co.ke")
        # Get David's team employee_ids via widget
        w = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20).json()
        allowed_ids = {w["manager_employee_id"]} | {t["id"] for t in w["team"]}

        r = s.get(f"{BASE}/api/leave", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        # Every row's employee_id must be inside allowed_ids
        leaked = [lr for lr in rows if lr.get("employee_id") not in allowed_ids]
        assert not leaked, f"manager leave list LEAKED rows outside team: {[(l.get('employee_id'), l.get('id')) for l in leaked][:5]}"


# ---------- Integration regression: IDs must be consistent across endpoints ----------
class TestIdConsistency:
    """
    The Line Manager dashboard renders clickable rows that navigate to
    /employees/<id>. The id in the widget MUST be the same id returned by
    /api/employees so the detail page can locate the employee.
    """

    def test_widget_ids_match_employees_list_ids(self):
        s = login("manager@solvit.co.ke")
        widget = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20).json()
        rows = s.get(f"{BASE}/api/employees", timeout=20).json()

        list_by_name = {e["full_name"]: e.get("id") for e in rows}
        mismatches = []
        for t in widget["team"]:
            list_id = list_by_name.get(t["full_name"])
            if list_id and list_id != t["id"]:
                mismatches.append((t["full_name"], t["id"], list_id))
        assert not mismatches, (
            "Line-Manager widget IDs do NOT match /api/employees ids "
            "(widget rows will navigate to wrong /employees/<id> URL): "
            f"{mismatches}"
        )

    def test_employees_list_does_not_leak_mongodb_id(self):
        s = login("manager@solvit.co.ke")
        rows = s.get(f"{BASE}/api/employees", timeout=20).json()
        leaks = [e["full_name"] for e in rows if "_id" in e]
        assert not leaks, f"/api/employees response leaks Mongo _id for: {leaks}"

    def test_employee_detail_reachable_for_lm_direct_report(self):
        """LM dashboard row click → /employees/<id>; the GET must work."""
        s = login("manager@solvit.co.ke")
        widget = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20).json()
        assert widget["team"], "manager should have team"
        report_id = widget["team"][0]["id"]
        # Frontend page calls /api/employees/{id}/profile then /api/employees/{id}
        r_simple = s.get(f"{BASE}/api/employees/{report_id}", timeout=20)
        r_profile = s.get(f"{BASE}/api/employees/{report_id}/profile", timeout=20)
        # Both endpoints must succeed (200) for the direct report
        assert r_simple.status_code == 200, (
            f"GET /employees/{report_id} returned {r_simple.status_code}: {r_simple.text[:200]}"
        )
        assert r_profile.status_code == 200, (
            f"GET /employees/{report_id}/profile returned {r_profile.status_code}: {r_profile.text[:200]}"
        )

    def test_employees_list_no_id_leak_across_roles(self):
        """Iter 15 retest: every list endpoint response must use UUID id and not leak _id."""
        for email in [
            "jessica@solvit.co.ke",
            "finance@solvit.co.ke",
            "employee@solvit.co.ke",
            "manager@solvit.co.ke",
            "solver@solvit.co.ke",
            "itadmin@solvit.co.ke",
            "board@solvit.co.ke",
        ]:
            s = login(email)
            r = s.get(f"{BASE}/api/employees", timeout=20)
            assert r.status_code == 200, f"{email}: {r.status_code} {r.text}"
            rows = r.json()
            for e in rows:
                assert "_id" not in e, f"{email}: row leaks _id: {e.get('full_name')}"
                # id must be a UUID (36 chars with hyphens), not a 24-char ObjectId hex
                eid = e.get("id")
                assert eid is not None, f"{email}: row missing id: {e}"
                assert "-" in eid and len(eid) == 36, (
                    f"{email}: row id is not a UUID (looks like ObjectId): {eid} for {e.get('full_name')}"
                )

    def test_get_employee_by_id_matches_list_id(self):
        """GET /api/employees/{id} should 200 and return the same UUID id."""
        s = login("jessica@solvit.co.ke")
        rows = s.get(f"{BASE}/api/employees", timeout=20).json()
        # Pick a non-board employee
        target = next((e for e in rows if e.get("full_name") == "James Kamau"), rows[0])
        eid = target["id"]
        r = s.get(f"{BASE}/api/employees/{eid}", timeout=20)
        assert r.status_code == 200, f"GET /employees/{eid} status={r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body.get("id") == eid, f"detail.id={body.get('id')} != list.id={eid}"
        assert "_id" not in body, f"detail leaks _id: {body.keys()}"


# ---------- Scope enforcement on /employees/{id} and /profile ----------
class TestLineManagerScope:
    def _manager_session_and_team(self):
        s = login("manager@solvit.co.ke")
        widget = s.get(f"{BASE}/api/dashboard/line-manager", timeout=20).json()
        return s, widget

    def test_lm_profile_direct_report_200(self):
        s, widget = self._manager_session_and_team()
        # Pick James Kamau or Robert Kiprotich
        report = next((t for t in widget["team"] if t["full_name"] in ("James Kamau", "Robert Kiprotich")), None)
        assert report is not None, f"no direct report found in widget team {widget['team']}"
        r = s.get(f"{BASE}/api/employees/{report['id']}/profile", timeout=20)
        assert r.status_code == 200, f"profile returned {r.status_code}: {r.text[:200]}"
        body = r.json()
        emp = body.get("employee") or {}
        assert emp.get("id") == report["id"], f"profile employee.id mismatch: {emp.get('id')} vs {report['id']}"
        assert emp.get("full_name") == report["full_name"]

    def test_lm_profile_not_direct_report_403(self):
        # manager@ should NOT be able to fetch Mary Wanjiru's profile (reports to Lillian)
        s = login("manager@solvit.co.ke")
        # Need Mary's id — fetch via HR Admin
        hr = login("jessica@solvit.co.ke")
        rows = hr.get(f"{BASE}/api/employees", timeout=20).json()
        mary = next((e for e in rows if e.get("full_name") == "Mary Wanjiru"), None)
        if mary is None:
            pytest.skip("Mary Wanjiru not in seed data")
        r = s.get(f"{BASE}/api/employees/{mary['id']}/profile", timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_lm_detail_not_direct_report_403(self):
        s = login("manager@solvit.co.ke")
        hr = login("jessica@solvit.co.ke")
        rows = hr.get(f"{BASE}/api/employees", timeout=20).json()
        sarah = next((e for e in rows if e.get("full_name") == "Sarah Njoroge"), None)
        assert sarah is not None, "Sarah Njoroge not in seed data"
        r = s.get(f"{BASE}/api/employees/{sarah['id']}", timeout=20)
        assert r.status_code == 403, f"expected 403 for non-report detail, got {r.status_code}: {r.text[:200]}"

    def test_widget_team_ids_match_employees_uuid(self):
        """Iter 15 retest: widget team[].id must match the UUID from /api/employees."""
        hr = login("jessica@solvit.co.ke")
        all_rows = hr.get(f"{BASE}/api/employees", timeout=20).json()
        by_name = {e["full_name"]: e["id"] for e in all_rows}

        s, widget = self._manager_session_and_team()
        for t in widget["team"]:
            canonical = by_name.get(t["full_name"])
            assert canonical, f"{t['full_name']} not in HR employees list"
            assert t["id"] == canonical, (
                f"widget id {t['id']} != canonical {canonical} for {t['full_name']}"
            )
