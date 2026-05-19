import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""Iteration 3 — workflow matrix enforcement, 9-Box correction, Talent Density, Voluntary Attrition, MyTasks."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://solvit-people-mgmt.preview.emergentagent.com').rstrip('/')


def _login(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": _DEMO_PWD}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def hr_session():
    return _login("jessica@solvit.co.ke")


@pytest.fixture(scope="session")
def emp_session():
    return _login("employee@solvit.co.ke")


@pytest.fixture(scope="session")
def mgr_session():
    return _login("manager@solvit.co.ke")


# ---------------- Forms list with workflow metadata ----------------
class TestFormsListMetadata:
    def test_forms_returns_32_with_workflow(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 32, f"Expected >=32 forms, got {len(data)}"
        sample = data[0]
        for k in ["module", "module_name", "workflow_trigger", "completing_users_sequence", "required_signatures", "outcome_rule"]:
            assert k in sample, f"Missing key {k} in forms response"

    def test_form06_workflow(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-06")
        assert r.status_code == 200
        d = r.json()
        assert d["completing_users_sequence"] == ["employee", "line_manager", "hr_admin"]
        assert d["required_signatures"] == ["employee", "line_manager", "hr_admin"]
        assert d["outcome_rule"] == "review.completed"

    def test_form15_three_step(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-15")
        assert r.status_code == 200
        d = r.json()
        assert len(d["completing_users_sequence"]) == 3
        assert d["completing_users_sequence"] == ["employee", "line_manager", "hr_admin"]

    def test_form23_sections_and_finance(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-23")
        assert r.status_code == 200
        d = r.json()
        assert "finance" in d.get("required_signatures", [])
        sections = d.get("sections", [])
        assert len(sections) == 4
        roles = {s.get("accessible_by_role") for s in sections}
        # at least some sections must be tagged with employee/line_manager/finance/hr_admin
        assert "finance" in roles or any("finance" in str(r).lower() for r in roles)


# ---------------- Sequential signing flow form-15 ----------------
class TestFormWorkflowSigning:
    submission_id = None

    def test_a_start_form15(self, hr_session):
        # Get an employee id
        emps = hr_session.get(f"{BASE_URL}/api/employees").json()
        emp_id = emps[0].get("id") if emps else "TEST_emp"
        r = hr_session.post(f"{BASE_URL}/api/forms/form-15/start",
                            json={"employee_id": emp_id, "employee_name": "TEST Emp", "data": {"leave_type": "Annual"}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "InProgress"
        assert d["current_step_index"] == 0
        assert d["next_required_role"] == "employee"
        TestFormWorkflowSigning.submission_id = d["id"]

    def test_b_sign_step1_employee(self, hr_session):
        sid = TestFormWorkflowSigning.submission_id
        assert sid
        r = hr_session.post(f"{BASE_URL}/api/forms/submissions/{sid}/sign",
                            json={"signature": "Jessica acting as Employee"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["next_required_role"] == "line_manager"
        assert "employee" in d["signatures"]

    def test_c_sign_step2_line_manager(self, mgr_session):
        sid = TestFormWorkflowSigning.submission_id
        r = mgr_session.post(f"{BASE_URL}/api/forms/submissions/{sid}/sign", json={"signature": "Mgr"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["next_required_role"] == "hr_admin"
        assert "line_manager" in d["signatures"]

    def test_d_sign_step3_hr_admin_completes(self, hr_session):
        sid = TestFormWorkflowSigning.submission_id
        r = hr_session.post(f"{BASE_URL}/api/forms/submissions/{sid}/sign", json={"signature": "HR"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "Completed"
        assert d.get("next_required_role") in (None,)
        for k in ["employee", "line_manager", "hr_admin"]:
            assert k in d["signatures"], f"Missing signature {k}"


class TestSubmitMissingSigs:
    def test_submit_missing_required_returns_400(self, hr_session):
        r = hr_session.post(f"{BASE_URL}/api/forms/form-15/submit",
                            json={"data": {"leave_type": "Annual"}, "signatures": {}})
        assert r.status_code == 400
        msg = r.json().get("detail", "")
        assert "Missing required signatures" in msg


class TestMyTasks:
    def test_my_tasks_returns_list(self, mgr_session):
        # Create a fresh submission so manager has a pending task
        emps = mgr_session.get(f"{BASE_URL}/api/employees").json()
        emp_id = emps[0].get("id") if emps else "TEST_emp"
        start = mgr_session.post(f"{BASE_URL}/api/forms/form-15/start",
                                 json={"employee_id": emp_id, "employee_name": "TEST Emp"})
        assert start.status_code == 200
        sid = start.json()["id"]
        # employee step (manager not employee role; route checks role_match — should fail unless hr override)
        # Use HR session to advance through employee step
        hr = _login("jessica@solvit.co.ke")
        sign1 = hr.post(f"{BASE_URL}/api/forms/submissions/{sid}/sign", json={"signature": "HR-asEmp"})
        assert sign1.status_code == 200
        # Now next_required_role should be line_manager
        r = mgr_session.get(f"{BASE_URL}/api/forms/my-tasks")
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list)
        ids = [t.get("id") for t in tasks]
        assert sid in ids


# ---------------- Talent Density ----------------
class TestTalentDensity:
    def test_hr_admin_can_access(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/performance/talent-density")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["score_pct", "target_pct", "status", "components", "active_employees", "in_target_quadrant", "cycle_year"]:
            assert k in d, f"Missing key {k}"
        assert d["target_pct"] == 85
        comps = d["components"]
        for k in ["primary_stars_core_pct", "secondary_values_avg_pct", "tertiary_alignment_pct"]:
            assert k in comps

    def test_employee_forbidden(self, emp_session):
        r = emp_session.get(f"{BASE_URL}/api/performance/talent-density")
        assert r.status_code == 403


# ---------------- Voluntary Attrition ----------------
class TestVoluntaryAttrition:
    def test_hr_admin_can_access(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/retention/voluntary-attrition")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["voluntary_count_12mo", "avg_headcount", "pct", "target_pct", "status", "regrettable", "non_regrettable", "probation_exits_excluded"]:
            assert k in d, f"Missing key {k}"
        assert d["target_pct"] == 10
        assert d["status"] in ("Healthy", "Concerning", "Critical")
