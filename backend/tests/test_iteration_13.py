"""
Iteration 13 — Retest after enforce_line_manager_hierarchy() seed fix.

Scope:
- /api/employees/me line_manager_name resolves correctly for all 6 accounts
- Re-validate mandatory line_manager_id (422 missing, 400 invalid, 201 valid)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PWD = "Solvit@2026"


def login(email):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


# Hierarchy assertions per review_request
EXPECTED_HIERARCHY = {
    "jessica@solvit.co.ke": "Michael Omondi",
    "manager@solvit.co.ke": "Sarah Njoroge",
    "finance@solvit.co.ke": "Michael Omondi",
    "employee@solvit.co.ke": "David Ochieng",
    "md@solvit.co.ke": "Board Chair",
    "ed@solvit.co.ke": "Board Chair",
}


class TestHierarchy:
    @pytest.mark.parametrize("email,expected_lm", list(EXPECTED_HIERARCHY.items()))
    def test_me_line_manager_name(self, email, expected_lm):
        s = login(email)
        r = s.get(f"{BASE}/api/employees/me", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        got = data.get("line_manager_name")
        assert got == expected_lm, f"{email}: expected '{expected_lm}', got '{got}' | full row: {data}"


class TestMandatoryLM:
    def test_missing_lm_returns_422(self):
        s = login("jessica@solvit.co.ke")
        ts = int(time.time())
        payload = {
            "full_name": "UAT13 Missing LM",
            "work_email": f"uat13-no-lm-{ts}@solvit.co.ke",
            "department": "Operations",
            "role_title": "Test",
            "role_level": "L2",
            "start_date": "2026-02-01",
        }
        r = s.post(f"{BASE}/api/employees", json=payload, timeout=20)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_bad_lm_returns_400(self):
        s = login("jessica@solvit.co.ke")
        ts = int(time.time())
        payload = {
            "full_name": "UAT13 Bad LM",
            "work_email": f"uat13-bad-lm-{ts}@solvit.co.ke",
            "department": "Operations",
            "role_title": "Test",
            "role_level": "L2",
            "start_date": "2026-02-01",
            "line_manager_id": "507f1f77bcf86cd799439011",
        }
        r = s.post(f"{BASE}/api/employees", json=payload, timeout=20)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_valid_lm_succeeds_and_persists(self):
        s = login("jessica@solvit.co.ke")
        rows = s.get(f"{BASE}/api/employees", timeout=20).json()
        assert rows
        # Pick David Ochieng as a stable LM
        lm = next((e for e in rows if e.get("full_name") == "David Ochieng"), rows[0])
        lm_id = lm["id"]
        ts = int(time.time())
        email = f"uat13-ok-lm-{ts}@solvit.co.ke"
        payload = {
            "full_name": "UAT13 Valid LM",
            "work_email": email,
            "department": "Operations",
            "role_title": "Test",
            "role_level": "L2",
            "start_date": "2026-02-01",
            "line_manager_id": lm_id,
        }
        r = s.post(f"{BASE}/api/employees", json=payload, timeout=20)
        assert r.status_code in (200, 201), f"expected 200/201 got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("line_manager_id") == lm_id
        # Verify persistence via list
        rows2 = s.get(f"{BASE}/api/employees?search=UAT13", timeout=20).json()
        created = next((e for e in rows2 if e.get("work_email") == email), None)
        assert created is not None, f"created employee not found in list"
        assert created.get("line_manager_id") == lm_id
