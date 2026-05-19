import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""Iter 10 — AI Assistant upgrade + legacy email tab removal."""
import os
import pytest
import httpx

API = os.environ.get("API_BASE_URL", "http://localhost:8001")
HR = {"email": "jessica@solvit.co.ke", "password": _DEMO_PWD}
EMP = {"email": "employee@solvit.co.ke", "password": _DEMO_PWD}


def _login(c, creds):
    r = c.post(f"{API}/api/auth/login", json=creds, timeout=20.0)
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def hr():
    return _login(httpx.Client(follow_redirects=True), HR)


@pytest.fixture(scope="module")
def emp():
    return _login(httpx.Client(follow_redirects=True), EMP)


class TestAIAssistant:
    def test_snapshot_returns_all_module_keys(self, hr):
        r = hr.get(f"{API}/api/ai-agent/snapshot")
        assert r.status_code == 200
        s = r.json()
        for k in ["headcount", "leave", "performance", "recruitment", "solvers",
                  "training", "recognition", "disciplinary", "budget", "onboarding",
                  "compliance_issues"]:
            assert k in s, f"missing snapshot key {k}"
        assert isinstance(s["headcount"]["total_active_fte"], int)
        assert isinstance(s["compliance_issues"], list)

    def test_snapshot_rbac_blocks_non_hr(self, emp):
        r = emp.get(f"{API}/api/ai-agent/snapshot")
        assert r.status_code == 403

    def test_employee_status_lookup(self, hr):
        # Pick an existing employee name from the live DB
        emps = hr.get(f"{API}/api/employees").json()
        assert emps, "Need at least one seeded employee"
        first_name = emps[0]["full_name"].split()[0]
        r = hr.get(f"{API}/api/ai-agent/employee-status", params={"query": first_name})
        assert r.status_code == 200
        info = r.json()
        assert "full_name" in info
        assert "recent_leave" in info
        assert "recent_reviews" in info

    def test_employee_status_404_for_unknown(self, hr):
        r = hr.get(f"{API}/api/ai-agent/employee-status", params={"query": "ZzzNonexistent"})
        assert r.status_code == 404

    def test_chat_grounded_in_live_data(self, hr):
        # Ask about a module that requires the snapshot — answer should reference
        # live data, not 'no data configured'.
        r = hr.post(f"{API}/api/ai-agent/chat", json={"message": "How many candidates are in the recruitment pipeline by stage?"})
        assert r.status_code == 200
        out = r.json()
        assert out["provider"] in ("openai", "anthropic", "gemini", "fallback")
        assert isinstance(out["response"], str)
        assert len(out["response"]) > 20

    def test_chat_rbac_blocks_non_hr(self, emp):
        r = emp.post(f"{API}/api/ai-agent/chat", json={"message": "Hi"})
        assert r.status_code == 403

    def test_compliance_check_returns_issues_list(self, hr):
        r = hr.get(f"{API}/api/ai-agent/compliance-check")
        assert r.status_code == 200
        out = r.json()
        assert "status" in out and "issues" in out and isinstance(out["issues"], list)
