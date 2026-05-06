"""Iteration 6 — Masters Settings module + Budget variance-on-Spent fix.

Run: pytest /app/backend/tests/test_iteration_6.py -v
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://solvit-people-mgmt.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = "Solvit@2026"

USERS = {
    "it_admin":      "itadmin@solvit.co.ke",
    "hr_admin":      "jessica@solvit.co.ke",
    "line_manager":  "manager@solvit.co.ke",
    "finance":       "finance@solvit.co.ke",
    "employee":      "employee@solvit.co.ke",
    "executive":     "md@solvit.co.ke",
}


def _login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def it_admin():
    return _login(USERS["it_admin"])


@pytest.fixture(scope="module")
def hr_admin():
    return _login(USERS["hr_admin"])


@pytest.fixture(scope="module")
def finance():
    return _login(USERS["finance"])


@pytest.fixture(scope="module")
def employee():
    return _login(USERS["employee"])


@pytest.fixture(scope="module")
def line_manager():
    return _login(USERS["line_manager"])


# ---------------- Auth / IT Admin seed ---------------------------------------
class TestItAdminLogin:
    def test_it_admin_login_and_me(self, it_admin):
        me = it_admin.get(f"{API}/auth/me", timeout=15)
        assert me.status_code == 200, me.text
        data = me.json()
        assert data.get("role") == "it_admin", f"expected role=it_admin got {data.get('role')}"
        assert data.get("email") == USERS["it_admin"]


# ---------------- Settings list ----------------------------------------------
class TestSettingsList:
    def test_it_admin_full_write(self, it_admin):
        r = it_admin.get(f"{API}/settings/masters", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["my_role"] == "it_admin"
        assert len(d["categories"]) == 11, f"expected 11 categories got {len(d['categories'])}"
        # All 11 write_access true
        wa = d["write_access"]
        assert all(wa.values()), f"IT Admin should have write on ALL: {wa}"

    def test_hr_admin_section_write(self, hr_admin):
        r = hr_admin.get(f"{API}/settings/masters", timeout=15)
        assert r.status_code == 200
        wa = r.json()["write_access"]
        expected_true = {"performance", "onboarding", "recruitment", "alignment_surveys", "retention", "recognition", "lookups"}
        for cat, val in wa.items():
            if cat in expected_true:
                assert val is True, f"hr_admin should have write on {cat}"
            else:
                assert val is False, f"hr_admin should NOT have write on {cat}"

    def test_finance_only_budget(self, finance):
        r = finance.get(f"{API}/settings/masters", timeout=15)
        assert r.status_code == 200
        wa = r.json()["write_access"]
        for cat, val in wa.items():
            if cat == "budget_compensation":
                assert val is True
            else:
                assert val is False, f"finance should NOT have write on {cat}"

    def test_employee_forbidden(self, employee):
        r = employee.get(f"{API}/settings/masters", timeout=15)
        assert r.status_code == 403


# ---------------- Category fetch ---------------------------------------------
class TestCategoryFetch:
    def test_organisation_defaults(self, it_admin):
        r = it_admin.get(f"{API}/settings/masters/organisation", timeout=15)
        assert r.status_code == 200, r.text
        v = r.json()["values"]
        assert v["company_name"] == "Solvit Limited"
        assert v["probation_period_months"] == 3
        assert isinstance(v["paye_brackets"], list) and len(v["paye_brackets"]) == 5
        assert isinstance(v["nhif_rates"], list) and len(v["nhif_rates"]) == 17
        assert isinstance(v["notice_period_by_level"], list) and len(v["notice_period_by_level"]) == 5

    def test_get_all_returns_11(self, it_admin):
        r = it_admin.get(f"{API}/settings/masters/all", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert len(d.keys()) == 11, f"expected 11 keys got {list(d.keys())}"


# ---------------- Update + cross-module integration --------------------------
class TestUpdateAndIntegration:
    def test_put_budget_envelope_60_then_envelope_endpoint_reflects(self, it_admin, finance):
        # Read current
        cur = it_admin.get(f"{API}/settings/masters/budget_compensation", timeout=15).json()["values"]
        cur["people_cost_envelope_pct_of_gp"] = 60
        r = it_admin.put(f"{API}/settings/masters/budget_compensation", json={"values": cur}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["changes"], list) and len(body["changes"]) >= 1

        # Live integration
        env = finance.get(f"{API}/budget/envelope", timeout=15)
        assert env.status_code == 200, env.text
        ed = env.json()
        assert ed.get("envelope_pct_of_gp") == 60, f"expected 60 got {ed.get('envelope_pct_of_gp')}"
        actual_gp = ed.get("actual_gp_kes") or ed.get("current_gp_actual_kes") or 0
        people_env = ed.get("people_cost_envelope_kes") or 0
        if actual_gp:
            assert abs(people_env - actual_gp * 0.6) < 1.0, f"envelope_kes mismatch: {people_env} vs {actual_gp*0.6}"

    def test_reset_envelope_to_50(self, it_admin, finance):
        cur = it_admin.get(f"{API}/settings/masters/budget_compensation", timeout=15).json()["values"]
        cur["people_cost_envelope_pct_of_gp"] = 50
        r = it_admin.put(f"{API}/settings/masters/budget_compensation", json={"values": cur}, timeout=15)
        assert r.status_code == 200
        env = finance.get(f"{API}/budget/envelope", timeout=15).json()
        assert env.get("envelope_pct_of_gp") == 50

    def test_hr_admin_cannot_edit_budget(self, hr_admin):
        cur_payload = {"values": {"people_cost_envelope_pct_of_gp": 55}}
        r = hr_admin.put(f"{API}/settings/masters/budget_compensation", json=cur_payload, timeout=15)
        assert r.status_code == 403
        assert "budget_compensation" in r.text.lower() or "cannot" in r.text.lower()

    def test_hr_admin_can_edit_performance_and_talent_density(self, hr_admin, it_admin):
        cur = hr_admin.get(f"{API}/settings/masters/performance", timeout=15).json()["values"]
        cur["talent_density_target_pct"] = 90
        r = hr_admin.put(f"{API}/settings/masters/performance", json={"values": cur}, timeout=15)
        assert r.status_code == 200, r.text

        td = hr_admin.get(f"{API}/performance/talent-density", timeout=15)
        assert td.status_code == 200, td.text
        assert td.json().get("target_pct") == 90

        # Reset to default 85
        cur["talent_density_target_pct"] = 85
        it_admin.put(f"{API}/settings/masters/performance", json={"values": cur}, timeout=15)

    def test_attrition_target_integration(self, hr_admin, it_admin):
        cur = hr_admin.get(f"{API}/settings/masters/retention", timeout=15).json()["values"]
        cur["attrition_target_pct"] = 15
        r = hr_admin.put(f"{API}/settings/masters/retention", json={"values": cur}, timeout=15)
        assert r.status_code == 200, r.text
        va = hr_admin.get(f"{API}/retention/voluntary-attrition", timeout=15)
        assert va.status_code == 200, va.text
        assert va.json().get("target_pct") == 15
        # reset
        cur["attrition_target_pct"] = 10
        it_admin.put(f"{API}/settings/masters/retention", json={"values": cur}, timeout=15)

    def test_allocation_threshold_integration(self, it_admin, hr_admin, finance):
        # Set threshold to 100000
        cur = it_admin.get(f"{API}/settings/masters/budget_compensation", timeout=15).json()["values"]
        cur["allocation_finance_approval_threshold_kes"] = 100000
        r = it_admin.put(f"{API}/settings/masters/budget_compensation", json={"values": cur}, timeout=15)
        assert r.status_code == 200, r.text

        # Try a 80000 allocation as HR (under threshold) → Approved
        a1 = hr_admin.post(f"{API}/budget/allocations", json={
            "purpose": "TEST_iter6_under", "amount_kes": 80000, "category": "Training"
        }, timeout=15)
        assert a1.status_code in (200, 201), a1.text
        d1 = a1.json()
        assert d1.get("status") == "Approved", f"under threshold expected Approved got {d1.get('status')}"

        # 120000 (over threshold) → Pending_Finance
        a2 = hr_admin.post(f"{API}/budget/allocations", json={
            "purpose": "TEST_iter6_over", "amount_kes": 120000, "category": "Training"
        }, timeout=15)
        assert a2.status_code in (200, 201), a2.text
        d2 = a2.json()
        assert d2.get("status") == "Pending_Finance", f"over threshold expected Pending_Finance got {d2.get('status')}"

        # Reset threshold
        cur["allocation_finance_approval_threshold_kes"] = 50000
        it_admin.put(f"{API}/settings/masters/budget_compensation", json={"values": cur}, timeout=15)


# ---------------- Audit log + reset ------------------------------------------
class TestAuditAndReset:
    def test_audit_log_it_admin(self, it_admin):
        r = it_admin.get(f"{API}/settings/masters/audit/log", timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for k in ("field", "old_value", "new_value", "changed_by_name", "timestamp"):
                assert k in row, f"audit row missing {k}"

    def test_audit_log_line_manager_forbidden(self, line_manager):
        r = line_manager.get(f"{API}/settings/masters/audit/log", timeout=15)
        assert r.status_code == 403

    def test_reset_organisation_it_admin(self, it_admin):
        r = it_admin.post(f"{API}/settings/masters/organisation/reset", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("reset") is True

    def test_reset_organisation_hr_admin_forbidden(self, hr_admin):
        r = hr_admin.post(f"{API}/settings/masters/organisation/reset", timeout=15)
        assert r.status_code == 403


# ---------------- Budget variance-on-Spent fix -------------------------------
class TestBudgetVarianceFix:
    def test_variance_returns_to_pool_on_spent(self, finance, hr_admin):
        # Baseline summary
        s0 = finance.get(f"{API}/budget/allocations/summary", timeout=15)
        assert s0.status_code == 200, s0.text
        rem0 = s0.json().get("remaining_kes", 0)

        # Create allocation 200000 (will be Pending_Finance under default threshold 50k)
        c = hr_admin.post(f"{API}/budget/allocations", json={
            "purpose": "TEST_iter6_variance", "amount_kes": 200000, "category": "Training"
        }, timeout=15)
        assert c.status_code in (200, 201), c.text
        alloc_id = c.json().get("id") or c.json().get("_id")
        assert alloc_id

        # Approve as Finance
        ap = finance.put(f"{API}/budget/allocations/{alloc_id}", json={"status": "Approved"}, timeout=15)
        assert ap.status_code == 200, ap.text

        # After approval, remaining should drop by 200k
        s1 = finance.get(f"{API}/budget/allocations/summary", timeout=15).json()
        rem1 = s1.get("remaining_kes", 0)
        assert rem1 < rem0, f"remaining should decrease after approval ({rem0} -> {rem1})"

        # Mark as Spent with spent_amount_kes=180000 (HR Admin marks Spent per route)
        sp = hr_admin.put(f"{API}/budget/allocations/{alloc_id}", json={
            "status": "Spent", "spent_amount_kes": 180000
        }, timeout=15)
        assert sp.status_code == 200, sp.text

        s2 = finance.get(f"{API}/budget/allocations/summary", timeout=15).json()
        rem2 = s2.get("remaining_kes", 0)
        # variance 20000 returned to pool
        delta = rem2 - rem1
        assert abs(delta - 20000) < 1.0, f"variance 20k should return to pool: rem after-approve={rem1} after-spent={rem2} delta={delta}"


# ---------------- Regression --------------------------------------------------
class TestRegression:
    def test_employees_list(self, hr_admin):
        r = hr_admin.get(f"{API}/employees", timeout=15)
        assert r.status_code == 200

    def test_forms_list(self, hr_admin):
        r = hr_admin.get(f"{API}/forms", timeout=15)
        assert r.status_code == 200

    def test_access_matrix(self, hr_admin):
        r = hr_admin.get(f"{API}/access/matrix", timeout=15)
        assert r.status_code == 200

    def test_review_panel(self, hr_admin):
        emps = hr_admin.get(f"{API}/employees", timeout=15).json()
        if not emps:
            pytest.skip("no employees")
        emp_id = emps[0].get("id") or emps[0].get("_id")
        r = hr_admin.get(f"{API}/performance/review-panel/{emp_id}", timeout=15)
        assert r.status_code == 200, r.text
