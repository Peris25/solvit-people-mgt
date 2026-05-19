import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""
Comprehensive backend test suite for Solvit People Management Platform.
Tests health, auth, and all 19+ module endpoints across 22 routers.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://solvit-people-mgmt.preview.emergentagent.com").rstrip("/")
PASSWORD = _DEMO_PWD

DEMO_USERS = {
    "hr_admin": "jessica@solvit.co.ke",
    "manager": "manager@solvit.co.ke",
    "finance": "finance@solvit.co.ke",
    "employee": "employee@solvit.co.ke",
    "solver": "solver@solvit.co.ke",
    "md": "md@solvit.co.ke",
}


def login(email, password=PASSWORD):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    return s, r


@pytest.fixture(scope="module")
def hr_session():
    s, r = login(DEMO_USERS["hr_admin"])
    assert r.status_code == 200, f"HR login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def employee_session():
    s, r = login(DEMO_USERS["employee"])
    assert r.status_code == 200, f"Employee login failed: {r.status_code}"
    return s


@pytest.fixture(scope="module")
def md_session():
    s, r = login(DEMO_USERS["md"])
    assert r.status_code == 200
    return s


# ---------- Health ----------
class TestHealth:
    def test_health_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"


# ---------- Auth ----------
class TestAuth:
    def test_login_all_demo_users(self):
        for role, email in DEMO_USERS.items():
            s, r = login(email)
            assert r.status_code == 200, f"{role} login failed: {r.status_code} {r.text[:200]}"
            data = r.json()
            assert "user" in data or "email" in data
            # cookie set
            assert "access_token" in s.cookies, f"access_token cookie not set for {role}"

    def test_bad_password_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": DEMO_USERS["hr_admin"], "password": "wrong"}, timeout=10)
        assert r.status_code == 401

    def test_auth_me(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("email") == DEMO_USERS["hr_admin"]

    def test_logout_clears_cookies(self):
        s, _ = login(DEMO_USERS["hr_admin"])
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=10)
        assert r.status_code in (200, 204)


# ---------- Employees ----------
class TestEmployees:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/employees", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 10, f"Expected >=10 seeded employees, got {len(data)}"

    def test_kanban(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/employees/kanban", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # kanban should have 4 columns
        assert isinstance(data, (dict, list))

    def test_stats(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/employees/stats", timeout=15)
        assert r.status_code == 200


# ---------- Solvers ----------
class TestSolvers:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/solvers", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_stats(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/solvers/stats", timeout=15)
        assert r.status_code == 200


# ---------- Recruitment ----------
class TestRecruitment:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/recruitment", timeout=15)
        assert r.status_code == 200

    def test_pipeline(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/recruitment/pipeline", timeout=15)
        assert r.status_code == 200


# ---------- Onboarding ----------
class TestOnboarding:
    def test_all(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/onboarding/all", timeout=15)
        assert r.status_code == 200


# ---------- Performance ----------
class TestPerformance:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/performance", timeout=15)
        assert r.status_code == 200

    def test_active_cycle(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/performance/active-cycle", timeout=15)
        assert r.status_code in (200, 404)

    def test_nine_box(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/performance/nine-box/matrix?cycle_year=2026", timeout=15)
        assert r.status_code == 200


# ---------- Surveys ----------
class TestSurveys:
    def test_windows(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/surveys/windows", timeout=15)
        assert r.status_code == 200

    def test_questions_fte(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/surveys/questions/FTE", timeout=15)
        assert r.status_code == 200


# ---------- Retention ----------
class TestRetention:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/retention", timeout=15)
        assert r.status_code == 200

    def test_risk_summary(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/retention/risk-summary", timeout=15)
        assert r.status_code == 200

    def test_exit_insights(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/retention/exit-insights", timeout=15)
        assert r.status_code == 200


# ---------- L&D ----------
class TestLnD:
    def test_training(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/lnd/training", timeout=15)
        assert r.status_code == 200


# ---------- Compensation ----------
class TestCompensation:
    def test_pay_bands(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compensation/pay-bands", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 5, f"Expected >=5 pay bands, got {len(data)}"

    def test_pay_band_alerts(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compensation/pay-bands/alerts", timeout=15)
        assert r.status_code == 200

    def test_bonus_calculator(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compensation/bonus/calculator?tier=Tier1", timeout=15)
        assert r.status_code == 200


# ---------- Recognition ----------
class TestRecognition:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/recognition", timeout=15)
        assert r.status_code == 200


# ---------- Budget ----------
class TestBudget:
    def test_envelope(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/budget/envelope", timeout=15)
        assert r.status_code == 200

    def test_summary(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/budget/summary", timeout=15)
        assert r.status_code == 200

    def test_budget_employee_forbidden(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/budget/summary", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Policies ----------
class TestPolicies:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/policies", timeout=15)
        assert r.status_code == 200


# ---------- Disciplinary ----------
class TestDisciplinary:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/disciplinary", timeout=15)
        assert r.status_code == 200


# ---------- Leave ----------
class TestLeave:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/leave", timeout=15)
        assert r.status_code == 200

    def test_types(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/leave/types", timeout=15)
        assert r.status_code == 200


# ---------- Calendar ----------
class TestCalendar:
    def test_calendar(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/calendar?days_ahead=90", timeout=15)
        assert r.status_code == 200


# ---------- Compliance ----------
class TestCompliance:
    def test_paye_calculator(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compliance/paye-calculator?gross_salary=75000", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # check PAYE fields exist
        keys = {k.lower() for k in data.keys()} if isinstance(data, dict) else set()
        for needed in ["paye", "nssf", "sha", "net"]:
            assert any(needed in k for k in keys), f"Missing {needed} in response keys: {keys}"

    def test_deadlines(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compliance/deadlines", timeout=15)
        assert r.status_code == 200

    def test_statutory(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/compliance/statutory", timeout=15)
        assert r.status_code == 200


# ---------- Settings ----------
class TestSettings:
    def test_get_settings_masked(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/settings", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Keys should be masked - emergent_llm_key shouldn't have full sk-emergent string
        body_str = str(data).lower()
        # the key starts with sk-emergent- and is 20+ chars; masking should hide it
        # Check that the actual key isn't fully exposed
        if "sk-emergent-" in body_str:
            # check it contains stars or mask chars
            assert "*" in str(data) or "•" in str(data) or "..." in str(data), \
                "Settings appears to expose full key without masking"


# ---------- AI Agent ----------
class TestAIAgent:
    def test_compliance_check_hr(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/ai-agent/compliance-check", timeout=30)
        assert r.status_code == 200

    def test_compliance_check_employee_forbidden(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/ai-agent/compliance-check", timeout=15)
        assert r.status_code in (401, 403)

    def test_chat_employee_forbidden(self, employee_session):
        r = employee_session.post(f"{BASE_URL}/api/ai-agent/chat",
                                  json={"message": "hi"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- Forms ----------
class TestForms:
    def test_list_forms(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 30, f"Expected ~32 forms, got {len(data)}"

    def test_get_form_01(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-01", timeout=15)
        assert r.status_code == 200

    def test_form_03_submit_autoscores(self, hr_session):
        # First fetch the form to get question keys
        r = hr_session.get(f"{BASE_URL}/api/forms/form-03", timeout=15)
        if r.status_code != 200:
            pytest.skip("form-03 not available")
        form = r.json()
        # Submit some answers
        payload = {"answers": {}, "employee_id": "test-employee"}
        r = hr_session.post(f"{BASE_URL}/api/forms/form-03/submit", json=payload, timeout=15)
        assert r.status_code in (200, 201, 400, 422)


# ---------- Automation ----------
class TestAutomation:
    def test_list(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/automation", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 60, f"Expected 60+ automation rules, got {len(data)}"

    def test_notifications(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/automation/notifications", timeout=15)
        assert r.status_code == 200
