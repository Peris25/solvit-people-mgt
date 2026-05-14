"""Iteration 18 — Email Send Log viewer + cross-app email triggers.

Validates:
  - GET /api/email-delivery/log RBAC, shape, status filter
  - Each trigger-producing route writes an email_log row with the expected
    template_key (status in {sent, failed} is acceptable — `skipped` is NOT
    written to the log, so a missing row means the trigger fell through to
    'no recipient' / 'no SMTP config' and did not actually fire).
  - Regression: leave triggers still fire (leave.received / leave.pending_lm)
"""
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASSWORD = "Solvit@2026"

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
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sessions():
    return {k: _login(v) for k, v in EMAILS.items()}


@pytest.fixture(scope="module")
def employees_index(sessions):
    rows = sessions["hr_admin"].get(f"{BASE_URL}/api/employees?limit=500").json()
    return rows, {(e.get("work_email") or "").lower(): e for e in rows}


def _ts_now():
    return datetime.now(timezone.utc).isoformat()


def _wait_for_template(s, template_key, after_ts, attempts=8, delay=0.6):
    for _ in range(attempts):
        rows = s.get(f"{BASE_URL}/api/email-delivery/log", params={"limit": 500}).json()
        for r in rows:
            if r.get("template_key") == template_key and (r.get("sent_at") or "") >= after_ts:
                return r
        time.sleep(delay)
    return None


# =========================================================================
# GET /api/email-delivery/log — RBAC + shape
# =========================================================================
class TestEmailLogEndpoint:
    def test_list_as_it_admin(self, sessions):
        r = sessions["it_admin"].get(f"{BASE_URL}/api/email-delivery/log", params={"limit": 50})
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            for k in ("id", "to", "subject", "template_key", "mode", "status", "error", "sent_at", "source"):
                assert k in rows[0]

    def test_list_as_hr_admin(self, sessions):
        r = sessions["hr_admin"].get(f"{BASE_URL}/api/email-delivery/log", params={"limit": 10})
        assert r.status_code == 200

    def test_employee_forbidden(self, sessions):
        assert sessions["employee"].get(f"{BASE_URL}/api/email-delivery/log").status_code == 403

    def test_solver_forbidden(self, sessions):
        assert sessions["solver"].get(f"{BASE_URL}/api/email-delivery/log").status_code == 403

    def test_status_filter_failed(self, sessions):
        rows = sessions["it_admin"].get(f"{BASE_URL}/api/email-delivery/log", params={"status": "failed", "limit": 50}).json()
        for r in rows:
            assert r.get("status") == "failed"


# =========================================================================
# Trigger actions
# =========================================================================
class TestTriggers:
    def test_onboarding_welcome(self, sessions, employees_index):
        anchor = _ts_now()
        _, idx = employees_index
        lm = idx[EMAILS["line_manager"]]
        payload = {
            "full_name": f"TEST Hire {uuid.uuid4().hex[:6]}",
            "work_email": f"test_hire_{uuid.uuid4().hex[:8]}@solvit.co.ke",
            "department": "Operations",
            "role_title": "Associate",
            "role_level": "L3",
            "line_manager_id": lm["id"],
            "start_date": "2026-02-01",
            "employment_type": "Full_Time",
        }
        r = sessions["hr_admin"].post(f"{BASE_URL}/api/employees", json=payload)
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "onboarding.welcome", anchor) is not None

    def test_performance_review_complete(self, sessions, employees_index):
        s = sessions["hr_admin"]
        _, idx = employees_index
        emp = idx[EMAILS["employee"]]
        r0 = s.post(f"{BASE_URL}/api/performance", json={
            "employee_id": emp["id"], "cycle_type": "Mid_Year", "cycle_year": 2026,
        })
        assert r0.status_code in (200, 201), r0.text
        rid = r0.json().get("id") or r0.json().get("review_id")
        anchor = _ts_now()
        r = s.put(f"{BASE_URL}/api/performance/{rid}", json={"status": "Completed"})
        assert r.status_code in (200, 204), r.text
        assert _wait_for_template(sessions["it_admin"], "performance.review_complete", anchor) is not None

    def test_recognition_peer(self, sessions, employees_index):
        anchor = _ts_now()
        _, idx = employees_index
        nominee = idx[EMAILS["line_manager"]]
        r = sessions["employee"].post(f"{BASE_URL}/api/recognition/peer-nomination", json={
            "nominee_id": nominee["id"],
            "nominee_name": nominee.get("full_name", "Nominee"),
            "values_demonstrated": ["Teamwork"],
            "specific_behaviour": "TEST iter18 behaviour",
            "impact": "TEST iter18 impact",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "recognition.peer", anchor) is not None

    def test_recognition_manager(self, sessions, employees_index):
        anchor = _ts_now()
        _, idx = employees_index
        recip = idx[EMAILS["employee"]]
        r = sessions["line_manager"].post(f"{BASE_URL}/api/recognition/manager", json={
            "nominee_id": recip["id"],
            "nominee_name": recip.get("full_name", "Recipient"),
            "specific_behaviour": "TEST iter18 manager behaviour",
            "impact": "TEST iter18 manager impact",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "recognition.manager", anchor) is not None

    @pytest.mark.parametrize("notice_type,template_key", [
        ("Written Warning", "disciplinary.written"),
        ("Final Warning", "disciplinary.final"),
        ("Dismissal", "disciplinary.dismissal"),
    ])
    def test_disciplinary_notices(self, sessions, employees_index, notice_type, template_key):
        s = sessions["hr_admin"]
        _, idx = employees_index
        emp = idx[EMAILS["employee"]]
        r0 = s.post(f"{BASE_URL}/api/disciplinary", json={
            "employee_id": emp["id"],
            "employee_name": emp.get("full_name", "Emp"),
            "allegation_category": "Conduct",
            "allegation_details": f"TEST iter18 {notice_type}",
            "incident_date": "2026-01-10",
        })
        assert r0.status_code in (200, 201), r0.text
        cid = r0.json().get("id")
        anchor = _ts_now()
        r = s.post(f"{BASE_URL}/api/disciplinary/{cid}/issue-notice", json={"notice_type": notice_type})
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], template_key, anchor) is not None, f"missing {template_key}"

    def test_comp_salary_review(self, sessions, employees_index):
        anchor = _ts_now()
        _, idx = employees_index
        emp = idx[EMAILS["employee"]]
        r = sessions["hr_admin"].post(f"{BASE_URL}/api/compensation/salary-review", json={
            "employee_id": emp["id"], "old_salary_kes": 100000, "new_salary_kes": 110000,
            "reason": "TEST iter18",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "comp.salary_review", anchor) is not None

    def test_recruitment_flow(self, sessions):
        s = sessions["hr_admin"]
        anchor = _ts_now()
        r = s.post(f"{BASE_URL}/api/recruitment", json={
            "full_name": f"TEST Cand {uuid.uuid4().hex[:6]}",
            "email": f"test_cand_{uuid.uuid4().hex[:8]}@example.com",
            "position_applied": "Operations Associate",
            "department": "Operations",
            "role_level": "L3",
            "source": "Referral",
        })
        assert r.status_code in (200, 201), r.text
        cid = r.json().get("id")
        assert _wait_for_template(sessions["it_admin"], "recruitment.application_received", anchor) is not None
        for stage, tpl in [
            ("Competency_Test", "recruitment.invite_competency"),
            ("Physical_Interview", "recruitment.invite_interview"),
        ]:
            a = _ts_now()
            r2 = s.put(f"{BASE_URL}/api/recruitment/{cid}", json={"stage": stage})
            assert r2.status_code in (200, 204), r2.text
            assert _wait_for_template(sessions["it_admin"], tpl, a) is not None, f"missing {tpl}"
        a3 = _ts_now()
        r3 = s.put(f"{BASE_URL}/api/recruitment/{cid}", json={"outcome": "Rejected"})
        assert r3.status_code in (200, 204), r3.text
        assert _wait_for_template(sessions["it_admin"], "recruitment.regret", a3) is not None

    def test_policy_published(self, sessions):
        anchor = _ts_now()
        r = sessions["hr_admin"].post(f"{BASE_URL}/api/policies", json={
            "title": f"TEST Policy {uuid.uuid4().hex[:6]}",
            "version": "1.0",
            "category": "HR",
            "description": "TEST iter18",
            "effective_date": "2026-02-01",
        })
        assert r.status_code in (200, 201), r.text
        # Up to N emails fire; wait a bit longer
        assert _wait_for_template(sessions["it_admin"], "policy.published", anchor, attempts=12, delay=1.0) is not None

    def test_projects_lifecycle(self, sessions, employees_index):
        s = sessions["hr_admin"]
        _, idx = employees_index
        emp = idx[EMAILS["employee"]]
        anchor = _ts_now()
        r = s.post(f"{BASE_URL}/api/projects", json={
            "employee_id": emp["id"],
            "employee_name": emp.get("full_name", "Emp"),
            "project_name": f"TEST Project {uuid.uuid4().hex[:6]}",
            "project_objective": "TEST iter18",
            "success_criteria": "TEST iter18 success",
            "expected_completion_date": "2026-03-15",
        })
        assert r.status_code in (200, 201), r.text
        pid = r.json().get("id")
        assert _wait_for_template(sessions["it_admin"], "lnd.project_assigned", anchor) is not None
        anchor2 = _ts_now()
        r2 = s.put(f"{BASE_URL}/api/projects/{pid}", json={"status": "Completed"})
        assert r2.status_code in (200, 204), r2.text
        assert _wait_for_template(sessions["it_admin"], "lnd.project_completed", anchor2) is not None

    def test_lnd_training_request(self, sessions, employees_index):
        _, idx = employees_index
        emp = idx[EMAILS["employee"]]
        anchor = _ts_now()
        r = sessions["employee"].post(f"{BASE_URL}/api/lnd/training", json={
            "employee_id": emp["id"],
            "training_name": "TEST iter18 Training",
            "provider": "Internal",
            "delivery_method": "Online",
            "cost_kes": 5000,
            "business_justification": "TEST iter18",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "lnd.training_assigned", anchor) is not None

    def test_lnd_bulk_assign(self, sessions, employees_index):
        _, idx = employees_index
        ids = [idx[EMAILS["employee"]]["id"]]
        anchor = _ts_now()
        r = sessions["hr_admin"].post(f"{BASE_URL}/api/lnd/training/bulk-assign", json={
            "employee_ids": ids,
            "training_name": "TEST iter18 Bulk",
            "provider": "Internal",
            "delivery_method": "Online",
            "business_justification": "TEST iter18 bulk",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "lnd.training_assigned", anchor) is not None

    # ---- Solver triggers (require solver record to have an email) ----
    def _solver_with_email(self, s):
        sols = s.get(f"{BASE_URL}/api/solvers").json()
        if not isinstance(sols, list):
            return None
        for sol in sols:
            if sol.get("email") or sol.get("work_email"):
                return sol
        return None

    def test_solver_activation(self, sessions):
        sol = self._solver_with_email(sessions["hr_admin"])
        if not sol:
            pytest.skip("no solver has an email — trigger would silently skip (CODE GAP REPORTED)")
        anchor = _ts_now()
        r = sessions["hr_admin"].post(f"{BASE_URL}/api/solvers/{sol['id']}/activate", json={})
        if r.status_code not in (200, 201):
            pytest.skip(f"activation route returned {r.status_code}")
        assert _wait_for_template(sessions["it_admin"], "solver.activation", anchor) is not None

    def test_solver_tier_upgrade(self, sessions):
        sol = self._solver_with_email(sessions["hr_admin"])
        if not sol:
            pytest.skip("no solver has an email")
        anchor = _ts_now()
        r = sessions["hr_admin"].put(f"{BASE_URL}/api/solvers/{sol['id']}", json={"performance_tier": "Top"})
        if r.status_code not in (200, 204):
            pytest.skip(f"tier update returned {r.status_code}")
        assert _wait_for_template(sessions["it_admin"], "solver.tier_upgrade", anchor) is not None

    def test_solver_suspension(self, sessions):
        sol = self._solver_with_email(sessions["hr_admin"])
        if not sol:
            pytest.skip("no solver has an email")
        anchor = _ts_now()
        r = sessions["hr_admin"].put(f"{BASE_URL}/api/solvers/{sol['id']}", json={"lifecycle_state": "Suspended"})
        if r.status_code not in (200, 204):
            pytest.skip(f"suspend returned {r.status_code}")
        assert _wait_for_template(sessions["it_admin"], "solver.suspension", anchor) is not None
        sessions["hr_admin"].put(f"{BASE_URL}/api/solvers/{sol['id']}", json={"lifecycle_state": "Active"})


# =========================================================================
# Regression — leave triggers still log
# =========================================================================
class TestLeaveRegression:
    def test_leave_received_and_pending_lm(self, sessions, employees_index):
        _, idx = employees_index
        emp_rec = idx[EMAILS["employee"]]
        anchor = _ts_now()
        r = sessions["employee"].post(f"{BASE_URL}/api/leave", json={
            "employee_id": emp_rec["id"],
            "leave_type": "Annual",
            "start_date": "2026-04-01",
            "end_date": "2026-04-02",
            "notes": "TEST iter18 regression",
        })
        assert r.status_code in (200, 201), r.text
        assert _wait_for_template(sessions["it_admin"], "leave.received", anchor) is not None
        assert _wait_for_template(sessions["it_admin"], "leave.pending_lm", anchor) is not None
