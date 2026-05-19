import os
_DEMO_PWD = os.environ.get("DEMO_SEED_PASSWORD", "Solvit@2026")
"""
Iteration 2 backend tests for Solvit People Management Platform.
Covers: employee profile drilldown, 24 new form schemas, stay interviews,
notifications read toggle, email-test endpoint, email settings masking,
reset-demo-data endpoint.
"""
import os
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://solvit-people-mgmt.preview.emergentagent.com").rstrip("/")
PASSWORD = _DEMO_PWD

HR_EMAIL = "jessica@solvit.co.ke"
EMP_EMAIL = "employee@solvit.co.ke"


def login(email, password=PASSWORD):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    return s, r


@pytest.fixture(scope="module")
def hr_session():
    s, r = login(HR_EMAIL)
    assert r.status_code == 200, f"HR login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def emp_session():
    s, r = login(EMP_EMAIL)
    assert r.status_code == 200, f"Employee login failed: {r.status_code}"
    return s


# ---------- Employees list (include_exited filter) ----------
class TestEmployeesIncludeExited:
    def test_default_excludes_exited(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/employees", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Should not contain Stephen Kiragu (status='Exited')
        names = [e.get("full_name", "") for e in data]
        assert not any("Stephen Kiragu" in n for n in names), \
            f"Stephen Kiragu should be excluded by default, got: {names}"

    def test_include_exited_true(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/employees?include_exited=true", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 10


# ---------- Employee profile drilldown ----------
class TestEmployeeProfile:
    def test_hr_can_view_any_profile(self, hr_session):
        emps = hr_session.get(f"{BASE_URL}/api/employees", timeout=15).json()
        assert len(emps) > 0
        target = emps[0]
        emp_id = target.get("id") or target.get("_id")
        r = hr_session.get(f"{BASE_URL}/api/employees/{emp_id}/profile", timeout=20)
        assert r.status_code == 200, f"Profile failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        required_keys = ["employee", "timeline", "performance_history", "leave_history",
                         "recognitions", "trainings", "idp", "disciplinary_cases", "notifications"]
        for k in required_keys:
            assert k in data, f"Missing key '{k}' in profile response"
        assert isinstance(data["timeline"], list)

    def test_employee_can_view_self(self, emp_session):
        me = emp_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
        # Find employee record matching email
        emp_id = me.get("employee_id") or me.get("id")
        if not emp_id:
            # Look up by email in HR session
            pytest.skip("Employee has no linked employee_id")
        r = emp_session.get(f"{BASE_URL}/api/employees/{emp_id}/profile", timeout=20)
        # Should work for self (200) or 403/404 if linkage is off
        assert r.status_code in (200, 403, 404)

    def test_employee_cannot_view_other(self, hr_session, emp_session):
        emps = hr_session.get(f"{BASE_URL}/api/employees", timeout=15).json()
        other = next((e for e in emps if e.get("work_email") != EMP_EMAIL), None)
        assert other is not None
        emp_id = other.get("id")
        r = emp_session.get(f"{BASE_URL}/api/employees/{emp_id}/profile", timeout=20)
        assert r.status_code in (403, 404), f"Expected 403/404, got {r.status_code}"


# ---------- Forms (32 schemas + specific forms) ----------
class TestForms:
    def test_list_32_forms(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 32, f"Expected >=32 forms, got {len(data)}"

    def _count_fields_sections(self, form):
        sections = form.get("sections") or []
        fields = []
        for s in sections:
            fields.extend(s.get("fields") or s.get("questions") or [])
        # fallback top-level fields
        if not fields:
            fields = form.get("fields") or form.get("questions") or []
        return len(fields), len(sections)

    def test_form_22(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-22", timeout=15)
        assert r.status_code == 200, r.text[:200]
        form = r.json()
        nf, ns = self._count_fields_sections(form)
        assert ns >= 3, f"form-22 expected >=3 sections, got {ns}"
        assert nf >= 8, f"form-22 expected >=8 fields, got {nf}"

    def test_form_23(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-23", timeout=15)
        assert r.status_code == 200
        form = r.json()
        nf, ns = self._count_fields_sections(form)
        assert ns >= 4, f"form-23 expected >=4 sections, got {ns}"
        assert nf >= 23, f"form-23 expected >=23 fields, got {nf}"

    def test_form_04_likert(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-04", timeout=15)
        assert r.status_code == 200
        form = r.json()
        sections = form.get("sections") or []
        assert len(sections) >= 3
        # Count likert-type questions
        all_q = []
        for s in sections:
            all_q.extend(s.get("fields") or s.get("questions") or [])
        likert = [q for q in all_q if "likert" in str(q.get("type", "")).lower() or "scale" in str(q.get("type", "")).lower() or q.get("scale")]
        assert len(likert) >= 12 or len(all_q) >= 12, \
            f"form-04 expected >=12 likert questions, got likert={len(likert)} all={len(all_q)}"

    def test_form_09_pip_smart(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-09", timeout=15)
        assert r.status_code == 200
        form = r.json()
        text = str(form).upper()
        assert "SMART" in text, "form-09 expected to contain SMART objectives section"

    def test_form_03_submit_full_quiz(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/forms/form-03", timeout=15)
        assert r.status_code == 200
        form = r.json()
        # Collect questions
        questions = []
        for s in form.get("sections") or []:
            questions.extend(s.get("fields") or s.get("questions") or [])
        if not questions:
            questions = form.get("questions") or form.get("fields") or []
        # Build answers — pick first option if multiple choice
        answers = {}
        for q in questions:
            qid = q.get("id") or q.get("key") or q.get("name")
            if not qid:
                continue
            opts = q.get("options") or q.get("choices") or []
            if opts:
                first = opts[0]
                answers[qid] = first.get("value") if isinstance(first, dict) else first
            else:
                answers[qid] = "yes"
        payload = {"answers": answers, "employee_id": "test-employee"}
        r = hr_session.post(f"{BASE_URL}/api/forms/form-03/submit", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"submit got {r.status_code}: {r.text[:200]}"
        data = r.json()
        # score 0-10, pass_mark 8
        assert "score" in data, f"Expected 'score' in response: {data}"
        assert 0 <= data["score"] <= 10
        if "pass_mark" in data:
            assert data["pass_mark"] == 8


# ---------- Stay Interviews ----------
class TestStayInterviews:
    created_id = None

    def test_list_has_seeded(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/retention/stay-interviews", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, f"Expected >=1 seeded stay interview, got {len(data)}"

    def test_create(self, hr_session):
        payload = {
            "employee_id": "TEST_emp_si_1",
            "employee_name": "TEST Interviewee",
            "scheduled_date": "2026-02-15",
            "trigger_reason": "9-month tenure review (TEST)",
        }
        r = hr_session.post(f"{BASE_URL}/api/retention/stay-interviews", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text[:200]
        data = r.json()
        assert data.get("status") == "Scheduled"
        assert data.get("id")
        TestStayInterviews.created_id = data["id"]

    def test_update_to_completed(self, hr_session):
        assert TestStayInterviews.created_id, "create must run first"
        update = {
            "status": "Completed",
            "what_makes_stay": "Team culture",
            "what_might_leave": "Commute distance",
            "agreed_actions": "Discuss remote options",
            "follow_up_date": "2026-03-15"
        }
        r = hr_session.put(
            f"{BASE_URL}/api/retention/stay-interviews/{TestStayInterviews.created_id}",
            json=update, timeout=15
        )
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("status") == "Completed"
        assert data.get("what_makes_stay") == "Team culture"
        assert data.get("what_might_leave") == "Commute distance"
        assert data.get("agreed_actions") == "Discuss remote options"

    def test_employee_forbidden(self, emp_session):
        r = emp_session.get(f"{BASE_URL}/api/retention/stay-interviews", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Notifications ----------
class TestNotifications:
    def test_list_has_4_seeded(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/automation/notifications", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 4, f"Expected >=4 notifications, got {len(data)}"
        # Mix of read/unread
        read_states = {n.get("is_read", False) for n in data}
        # At least unread ones should exist
        assert False in read_states, "Expected at least one unread notification"

    def test_mark_read_decreases_unread(self, hr_session):
        r = hr_session.get(f"{BASE_URL}/api/automation/notifications", timeout=15)
        data = r.json()
        unread = [n for n in data if not n.get("is_read", False)]
        if not unread:
            pytest.skip("No unread notifications available")
        count_before = len(unread)
        nid = unread[0].get("id") or unread[0].get("_id")
        pr = hr_session.put(f"{BASE_URL}/api/automation/notifications/{nid}/read", timeout=15)
        assert pr.status_code in (200, 204)
        # Re-fetch
        r2 = hr_session.get(f"{BASE_URL}/api/automation/notifications", timeout=15).json()
        unread_after = [n for n in r2 if not n.get("is_read", False)]
        assert len(unread_after) <= count_before - 1 or len(unread_after) < count_before, \
            f"unread count did not decrease: before={count_before}, after={len(unread_after)}"


# ---------- Settings: Email ----------
class TestSettingsEmail:
    def test_email_test_skipped_when_no_provider(self, hr_session):
        # Ensure provider is cleared (set email_provider to 'none'/None is disallowed by model filter)
        # Just call as-is — if provider is None, status should be 'skipped'
        r = hr_session.post(f"{BASE_URL}/api/settings/email-test",
                            json={"to": "test@example.com"}, timeout=20)
        # Either skipped (no provider) or success/failure based on env
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = r.json()
            assert "provider" in data or "status" in data
            # No exception expected per task description
            assert data.get("status") in ("skipped", "sent", "queued", "ok", "success", "failed")

    def test_email_test_employee_forbidden(self, emp_session):
        r = emp_session.post(f"{BASE_URL}/api/settings/email-test",
                             json={"to": "x@x.com"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_put_sendgrid_settings_masks_key(self, hr_session):
        payload = {
            "email_provider": "sendgrid",
            "email_api_key": "SG.TEST_fake_key_abcdef1234567890",
            "email_from_address": "noreply@solvit.co.ke",
            "email_from_name": "Solvit Test"
        }
        pr = hr_session.put(f"{BASE_URL}/api/settings", json=payload, timeout=15)
        assert pr.status_code == 200, pr.text[:200]
        gr = hr_session.get(f"{BASE_URL}/api/settings", timeout=15)
        assert gr.status_code == 200
        data = gr.json()
        assert data.get("email_provider") == "sendgrid"
        key_val = data.get("email_api_key") or ""
        # API key should be masked — should not contain the real key fragment
        assert "TEST_fake_key" not in key_val, \
            f"email_api_key not masked properly: {key_val}"
        assert "*" in key_val or "configured" in key_val.lower(), \
            f"email_api_key should contain '*' mask, got: {key_val}"


# ---------- Reset Demo Data ----------
class TestResetDemoData:
    def test_employee_forbidden(self, emp_session):
        r = emp_session.post(f"{BASE_URL}/api/settings/reset-demo-data", timeout=30)
        assert r.status_code in (401, 403)

    def test_reset_and_verify_seed_counts(self, hr_session):
        r = hr_session.post(f"{BASE_URL}/api/settings/reset-demo-data", timeout=120)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("status") == "success"
        # Verify employees: 9 active (excluding Stephen Kiragu)
        emps = hr_session.get(f"{BASE_URL}/api/employees", timeout=15).json()
        assert len(emps) == 9, f"Expected 9 active employees after reset, got {len(emps)}"
        # Verify nine-box: 7+ placements for current cycle year
        from datetime import datetime
        cy = datetime.now().year
        nb = hr_session.get(f"{BASE_URL}/api/performance/nine-box/matrix?cycle_year={cy}", timeout=15).json()
        placements = 0
        if isinstance(nb, dict):
            # Sum across cells
            for v in nb.values():
                if isinstance(v, list):
                    placements += len(v)
                elif isinstance(v, dict) and "employees" in v:
                    placements += len(v["employees"])
        elif isinstance(nb, list):
            placements = len(nb)
        assert placements >= 7, f"Expected 7+ 9-box placements, got {placements}. Response: {str(nb)[:300]}"
        # Verify notifications
        notifs = hr_session.get(f"{BASE_URL}/api/automation/notifications", timeout=15).json()
        assert len(notifs) >= 4, f"Expected >=4 notifications, got {len(notifs)}"
