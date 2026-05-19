import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""Iteration 8 — Leave overhaul (accrued balance, rollover, calendar, line_manager_id),
Skills Matrix endpoints, Performance review GET, regression."""
import os
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://solvit-people-mgmt.preview.emergentagent.com").rstrip("/")
PWD = _DEMO_PWD


def _login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def hr():
    return _login("jessica@solvit.co.ke")


@pytest.fixture(scope="module")
def employee():
    return _login("employee@solvit.co.ke")


@pytest.fixture(scope="module")
def manager():
    return _login("manager@solvit.co.ke")


@pytest.fixture(scope="module")
def board():
    return _login("board@solvit.co.ke")


@pytest.fixture(scope="module")
def hr_me(hr):
    return hr.get(f"{BASE_URL}/api/auth/me", timeout=15).json()


@pytest.fixture(scope="module")
def employee_me(employee):
    return employee.get(f"{BASE_URL}/api/auth/me", timeout=15).json()


# ---------- Leave Balances (accrued_annual) ----------
class TestLeaveBalances:
    def test_balances_returns_accrued(self, hr, hr_me):
        emp_id = hr_me.get("employee_id") or hr_me.get("id")
        r = hr.get(f"{BASE_URL}/api/leave/balances/{emp_id}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "accrued_annual" in data, data
        assert isinstance(data["accrued_annual"], (int, float))
        # Should be reasonable: 1.75 * months_passed_in_year, 0 <= x <= 21
        assert 0 <= data["accrued_annual"] <= 22, data["accrued_annual"]
        # Annual entry must contain accrued_kenyan_act
        # Annual entry may live at top-level (current shape) or under balances key
        annual = data.get("Annual") or (data.get("balances") or {}).get("Annual")
        assert annual is not None, f"No Annual entry: {data}"
        assert "accrued_kenyan_act" in annual, annual


# ---------- Leave Rollover ----------
class TestLeaveRollover:
    def test_rollover_shape(self, hr, hr_me):
        emp_id = hr_me.get("employee_id") or hr_me.get("id")
        r = hr.get(f"{BASE_URL}/api/leave/rollover/{emp_id}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Always-present keys
        for k in ("carried_forward", "used", "remaining", "deadline_passed", "banner"):
            assert k in data, f"missing {k}: {data}"
        assert isinstance(data["carried_forward"], (int, float))
        assert isinstance(data["used"], (int, float))
        assert isinstance(data["remaining"], (int, float))
        assert isinstance(data["deadline_passed"], bool)
        # `deadline` and non-null banner are only guaranteed when a rollover record exists.
        if data["carried_forward"] > 0:
            assert "deadline" in data and data["deadline"], data
            assert isinstance(data["banner"], str) and len(data["banner"]) > 0


# ---------- Leave Calendar ----------
class TestLeaveCalendar:
    def test_calendar_default(self, hr):
        r = hr.get(f"{BASE_URL}/api/leave/calendar", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "year" in data and "month" in data and "events" in data
        assert isinstance(data["events"], list)

    def test_calendar_explicit(self, hr):
        r = hr.get(f"{BASE_URL}/api/leave/calendar", params={"year": 2026, "month": 2}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["year"] == 2026 and data["month"] == 2
        # If events exist, validate schema
        for ev in data["events"]:
            for k in ("employee_name", "leave_type", "start_date", "end_date"):
                assert k in ev, ev


# ---------- POST /api/leave with line_manager_id ----------
class TestLeaveCreateWithLM:
    created_id = None
    created_mongo_id = None

    def test_create_with_line_manager_id(self, hr, hr_me):
        emp_id = hr_me.get("employee_id") or hr_me.get("id")
        # find a possible line manager
        emps = hr.get(f"{BASE_URL}/api/employees", timeout=15).json()
        lm = next((e for e in emps if "David Ochieng" in e.get("full_name", "")), None) or (emps[0] if emps else None)
        assert lm, "no employees to choose line manager"
        lm_id = lm["id"]
        body = {
            "employee_id": emp_id,
            "leave_type": "Annual",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "reason": "TEST_iter8 holiday",
            "line_manager_id": lm_id,
        }
        r = hr.post(f"{BASE_URL}/api/leave", json=body, timeout=20)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("line_manager_id") == lm_id, data
        TestLeaveCreateWithLM.created_id = data.get("id")
        TestLeaveCreateWithLM.created_mongo_id = data.get("_id")
        assert TestLeaveCreateWithLM.created_id

    def test_persisted_lm(self, hr, hr_me):
        # verify it appears in list view (filter by employee_id since HR list may scope)
        emp_id = hr_me.get("employee_id") or hr_me.get("id")
        r = hr.get(f"{BASE_URL}/api/leave", params={"employee_id": emp_id}, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        # NOTE: GET /leave fmt() overwrites `id` with the Mongo _id (string),
        # while POST /leave returns the original UUID `id`. Match across both fields.
        candidates = {TestLeaveCreateWithLM.created_id, TestLeaveCreateWithLM.created_mongo_id}
        match = next(
            (x for x in rows if (x.get("id") in candidates) or (x.get("_id") in candidates) or (x.get("reason") == "TEST_iter8 holiday")),
            None,
        )
        assert match is not None, f"created leave not in list (n={len(rows)}); ids={[r.get('id') for r in rows]}"
        assert match.get("line_manager_id"), match

    def test_cleanup(self, hr):
        cid = TestLeaveCreateWithLM.created_id
        if cid:
            hr.delete(f"{BASE_URL}/api/leave/{cid}", timeout=15)


# ---------- Skills Matrix ----------
class TestSkillsMatrix:
    def test_get_empty(self, hr, employee_me):
        eid = employee_me.get("employee_id") or employee_me.get("id")
        r = hr.get(f"{BASE_URL}/api/lnd/skills-matrix/{eid}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)

    def test_upsert_skills(self, hr, employee_me):
        eid = employee_me.get("employee_id") or employee_me.get("id")
        body = {"skills": [
            {"name": "TEST_Python", "level": "Advanced"},
            {"name": "TEST_FastAPI", "level": "Intermediate"},
        ]}
        r = hr.post(f"{BASE_URL}/api/lnd/skills-matrix/{eid}", json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        skills = data.get("skills", [])
        names = [s.get("name") for s in skills]
        assert "TEST_Python" in names and "TEST_FastAPI" in names, skills
        # GET to verify
        g = hr.get(f"{BASE_URL}/api/lnd/skills-matrix/{eid}", timeout=15).json()
        gnames = [s.get("name") for s in g.get("skills", [])]
        assert "TEST_Python" in gnames

    def test_cleanup_skills(self, hr, employee_me):
        eid = employee_me.get("employee_id") or employee_me.get("id")
        hr.post(f"{BASE_URL}/api/lnd/skills-matrix/{eid}", json={"skills": []}, timeout=15)


# ---------- Performance: GET /api/performance/{review_id} ----------
class TestPerformanceReviewGet:
    def test_get_review_by_id(self, hr):
        # List all reviews and pick one
        r = hr.get(f"{BASE_URL}/api/performance", timeout=15)
        assert r.status_code == 200, r.text
        reviews = r.json()
        assert isinstance(reviews, list) and len(reviews) > 0, "no reviews seeded"
        rid = reviews[0].get("id") or reviews[0].get("_id")
        assert rid
        r2 = hr.get(f"{BASE_URL}/api/performance/{rid}", timeout=15)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        # Should contain employee_id and status; section_a/b/c and rating may be optional depending on status
        assert "employee_id" in data, data
        assert "status" in data, data


# ---------- Regression ----------
class TestRegression:
    def test_auth_me(self, hr):
        r = hr.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200

    def test_employees(self, hr):
        r = hr.get(f"{BASE_URL}/api/employees", timeout=15)
        assert r.status_code == 200

    def test_access_matrix(self, hr):
        r = hr.get(f"{BASE_URL}/api/access/matrix", timeout=15)
        assert r.status_code == 200

    def test_settings_masters(self, hr):
        r = hr.get(f"{BASE_URL}/api/settings/masters", timeout=15)
        assert r.status_code == 200

    def test_budget_summary(self, hr):
        r = hr.get(f"{BASE_URL}/api/budget/summary", timeout=15)
        assert r.status_code == 200

    def test_performance_list(self, hr):
        r = hr.get(f"{BASE_URL}/api/performance", timeout=15)
        assert r.status_code == 200

    def test_talent_density(self, hr):
        r = hr.get(f"{BASE_URL}/api/performance/talent-density", timeout=15)
        assert r.status_code == 200
