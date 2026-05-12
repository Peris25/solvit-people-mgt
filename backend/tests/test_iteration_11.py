"""Iter 11 — Actionable AI Assistant with confirmation flow."""
import os
import pytest
import httpx

API = os.environ.get("API_BASE_URL", "http://localhost:8001")
HR = {"email": "jessica@solvit.co.ke", "password": "Solvit@2026"}
EMP = {"email": "employee@solvit.co.ke", "password": "Solvit@2026"}


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


def _propose(hr, msg):
    r = hr.post(f"{API}/api/ai-agent/chat", json={"message": msg})
    assert r.status_code == 200, r.text
    return r.json()


def _first_employee_name(hr):
    emps = hr.get(f"{API}/api/employees").json()
    assert emps, "Need at least one seeded employee"
    return emps[0]["full_name"]


class TestActionable:
    def test_send_recognition_propose_then_execute(self, hr):
        name = _first_employee_name(hr)
        d = _propose(hr, f"Send recognition to {name} for outstanding Q1 work")
        pa = d["proposed_action"]
        assert pa["kind"] == "send_recognition"
        assert pa["risk"] == "low"
        assert name in pa["summary"]
        # Execute (without overrides)
        r = hr.post(f"{API}/api/ai-agent/actions/{pa['id']}/execute", json={})
        assert r.status_code == 200
        assert r.json()["outcome"] == "executed"
        assert r.json()["result"]["ok"] is True

    def test_assign_training_propose_then_cancel(self, hr):
        name = _first_employee_name(hr)
        d = _propose(hr, f"Assign Safety Inspection training to {name}")
        pa = d["proposed_action"]
        assert pa["kind"] == "assign_training"
        assert "Safety Inspection" in pa["summary"]
        r = hr.post(f"{API}/api/ai-agent/actions/{pa['id']}/cancel")
        assert r.status_code == 200
        assert r.json()["outcome"] == "cancelled"
        # Same id can't be executed after cancel
        r2 = hr.post(f"{API}/api/ai-agent/actions/{pa['id']}/execute", json={})
        assert r2.status_code == 404

    def test_unknown_employee_returns_error_response(self, hr):
        d = _propose(hr, "Send recognition to ZZZNobody for hard work")
        assert d.get("proposed_action") is None
        assert "couldn't match" in d["response"].lower() or "couldn’t match" in d["response"].lower() or "no" in d["response"].lower()

    def test_non_hr_blocked_from_chat(self, emp):
        r = emp.post(f"{API}/api/ai-agent/chat", json={"message": "Approve leave"})
        assert r.status_code == 403

    def test_audit_records_outcomes(self, hr):
        # Propose + cancel one action so we know there's at least one audit row
        name = _first_employee_name(hr)
        d = _propose(hr, f"Send recognition to {name} for teamwork")
        pa = d["proposed_action"]
        hr.post(f"{API}/api/ai-agent/actions/{pa['id']}/cancel")
        r = hr.get(f"{API}/api/ai-agent/actions/audit")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        kinds = {row["kind"] for row in rows}
        assert "send_recognition" in kinds

    def test_send_email_requires_template_match(self, hr):
        name = _first_employee_name(hr)
        d = _propose(hr, f"Send the leave approved email to {name}")
        # Either proposes the action OR returns a helpful error message
        if d.get("proposed_action"):
            assert d["proposed_action"]["kind"] == "send_email"
            assert d["proposed_action"]["params"]["template_key"]
            assert d["proposed_action"]["risk"] == "medium"
            hr.post(f"{API}/api/ai-agent/actions/{d['proposed_action']['id']}/cancel")
        else:
            assert "template" in d["response"].lower()

    def test_execute_with_params_override(self, hr):
        """Editable fields (e.g. the recognition message) can be overridden at confirmation time."""
        name = _first_employee_name(hr)
        d = _propose(hr, f"Send recognition to {name} for general work")
        pa = d["proposed_action"]
        r = hr.post(f"{API}/api/ai-agent/actions/{pa['id']}/execute",
                    json={"params_override": {"message": "REVISED recognition copy"}})
        assert r.status_code == 200
        assert r.json()["outcome"] == "executed"
        # Verify the recognition record carries the override
        recs = hr.get(f"{API}/api/recognition", params={"employee_id": pa["params"]["employee_id"]}).json()
        latest = recs[0] if recs else {}
        assert "REVISED" in (latest.get("message") or ""), f"Override not applied — got {latest.get('message')}"
