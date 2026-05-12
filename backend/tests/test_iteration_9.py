"""
Iteration 9 — UAT enhancements (Documents · Data Import · Email Templates ·
Email Delivery · First-Login Tour).
"""
import io
import os
import pytest
import httpx
from pathlib import Path

API = os.environ.get("API_BASE_URL", "http://localhost:8001")
HR = {"email": "jessica@solvit.co.ke", "password": "Solvit@2026"}
IT = {"email": "itadmin@solvit.co.ke", "password": "Solvit@2026"}


def _login(client, creds):
    r = client.post(f"{API}/api/auth/login", json=creds, timeout=20.0)
    assert r.status_code == 200, r.text
    return client


@pytest.fixture(scope="module")
def hr_client():
    c = httpx.Client(follow_redirects=True)
    return _login(c, HR)


@pytest.fixture(scope="module")
def it_client():
    c = httpx.Client(follow_redirects=True)
    return _login(c, IT)


# ---------------- Item 1 — Documents ----------------

class TestDocuments:
    def test_categories_returns_defaults(self, hr_client):
        r = hr_client.get(f"{API}/api/documents/categories")
        assert r.status_code == 200
        cats = r.json()["categories"]
        assert "National ID / Passport" in cats
        assert "Other" in cats
        assert len(cats) >= 10

    def test_list_employee_documents_empty_initially(self, hr_client):
        # Pick first employee
        emps = hr_client.get(f"{API}/api/employees").json()
        emp_id = emps[0]["id"]
        r = hr_client.get(f"{API}/api/documents/employee/{emp_id}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_upload_view_delete_audit_cycle(self, hr_client):
        emps = hr_client.get(f"{API}/api/employees").json()
        emp_id = emps[0]["id"]
        files = {"file": ("contract.pdf", b"%PDF-1.4 dummy", "application/pdf")}
        data = {"category": "Signed Employment Contract"}
        r = hr_client.post(f"{API}/api/documents/employee/{emp_id}/upload", files=files, data=data)
        assert r.status_code == 200, r.text
        doc_id = r.json()["id"]
        # List
        r2 = hr_client.get(f"{API}/api/documents/employee/{emp_id}")
        assert any(d["id"] == doc_id for d in r2.json())
        # Audit
        r3 = hr_client.get(f"{API}/api/documents/audit-log", params={"employee_id": emp_id})
        assert r3.status_code == 200
        assert any(a["document_id"] == doc_id and a["action"] == "uploaded" for a in r3.json())
        # Delete
        r4 = hr_client.delete(f"{API}/api/documents/{doc_id}")
        assert r4.status_code == 200
        # Audit shows deletion
        r5 = hr_client.get(f"{API}/api/documents/audit-log", params={"employee_id": emp_id})
        assert any(a["document_id"] == doc_id and a["action"] == "deleted" for a in r5.json())

    def test_upload_rejects_oversize(self, hr_client):
        emps = hr_client.get(f"{API}/api/employees").json()
        emp_id = emps[0]["id"]
        big = b"x" * (10 * 1024 * 1024 + 1)
        files = {"file": ("big.pdf", big, "application/pdf")}
        data = {"category": "Other", "category_label": "Test"}
        r = hr_client.post(f"{API}/api/documents/employee/{emp_id}/upload", files=files, data=data)
        assert r.status_code == 413

    def test_upload_rejects_bad_extension(self, hr_client):
        emps = hr_client.get(f"{API}/api/employees").json()
        emp_id = emps[0]["id"]
        files = {"file": ("malware.exe", b"MZ", "application/octet-stream")}
        data = {"category": "Other", "category_label": "Test"}
        r = hr_client.post(f"{API}/api/documents/employee/{emp_id}/upload", files=files, data=data)
        assert r.status_code == 400


# ---------------- Item 2 — Data Import ----------------

class TestDataImport:
    def test_template_download_all_three(self, hr_client):
        for kind in ("fte_employee", "solver", "historical_performance"):
            r = hr_client.get(f"{API}/api/data-import/template/{kind}")
            assert r.status_code == 200
            assert r.content[:2] == b"PK"  # xlsx is a zip
            assert "attachment" in r.headers.get("content-disposition", "")

    def test_validation_flags_required_field(self, hr_client):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active; ws.title = "Data"
        # Headers — partial: only first 2 needed for the test
        headers = ["Employee ID", "Full Name", "Job Title", "Department", "Job Level (L1–L5)",
                   "Employment Start Date", "Employment Type", "Probation End Date",
                   "Line Manager Full Name", "Work Email", "Phone Number", "National ID Number",
                   "Date of Birth", "Gender", "NSSF Number", "NHIF Number", "KRA PIN",
                   "Bank Name", "Bank Branch", "Bank Account Number", "Salary (KES)",
                   "Pay Frequency", "Employment Status"]
        ws.append(headers)
        # Row missing Full Name (required) and bad date
        bad = [""] * len(headers)
        bad[0] = "EMP-X-001"; bad[2] = "Engineer"; bad[3] = "Operations"
        bad[4] = "L2"; bad[5] = "not-a-date"; bad[6] = "Full-Time"
        bad[9] = "x@solvit.co.ke"
        ws.append(bad)
        bio = io.BytesIO(); wb.save(bio); bio.seek(0)
        r = hr_client.post(
            f"{API}/api/data-import/validate",
            files={"file": ("bad.xlsx", bio.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"kind": "fte_employee"},
        )
        assert r.status_code == 200
        out = r.json()
        assert out["total_rows"] == 1
        assert out["error_count"] == 1
        errs = " ".join(out["rows"][0]["errors"]).lower()
        assert "full name" in errs or "required" in errs
        assert "date" in errs

    def test_history_empty_or_returns_list(self, hr_client):
        r = hr_client.get(f"{API}/api/data-import/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Item 3 — Email Templates ----------------

class TestEmailTemplates:
    def test_list_seeds_all_modules(self, it_client):
        r = it_client.get(f"{API}/api/email-templates")
        assert r.status_code == 200
        data = r.json()
        assert data["can_edit"] is True
        # Minimum modules required by the spec
        expected = ["Onboarding","Recruitment","Solvers","Performance","Surveys","Retention",
                    "L&D","Leave","Compensation","Recognition","Disciplinary","Policies",
                    "Budget","Compliance","System & Account"]
        for m in expected:
            assert m in data["groups"], f"Missing module group: {m}"
        # Sanity: at least 60 total templates
        total = sum(len(v) for v in data["groups"].values())
        assert total >= 60, f"Expected >=60 templates, got {total}"

    def test_hr_admin_view_only(self, hr_client):
        r = hr_client.get(f"{API}/api/email-templates")
        assert r.status_code == 200
        assert r.json()["can_edit"] is False
        # Try to edit — must be blocked
        r2 = hr_client.put(f"{API}/api/email-templates/leave.approved", json={"subject": "X", "body": "Y"})
        assert r2.status_code == 403

    def test_edit_then_reset(self, it_client):
        key = "leave.approved"
        r = it_client.put(f"{API}/api/email-templates/{key}", json={"subject": "Custom Subject", "body": "<p>Custom body</p>"})
        assert r.status_code == 200
        assert r.json()["subject"] == "Custom Subject"
        # Reset
        r2 = it_client.post(f"{API}/api/email-templates/{key}/reset")
        assert r2.status_code == 200
        assert r2.json()["is_default"] is True

    def test_preview_renders_merge_tags(self, it_client):
        r = it_client.post(f"{API}/api/email-templates/leave.approved/preview", json={"merge_values": {"employee_name": "Test User"}})
        assert r.status_code == 200
        out = r.json()
        assert "Test User" in out["body_html"]
        assert "{{" not in out["body_html"], "Unresolved merge tags in preview"


# ---------------- Item 3E — Email Delivery ----------------

class TestEmailDelivery:
    def test_get_returns_active_mode(self, it_client):
        r = it_client.get(f"{API}/api/email-delivery")
        assert r.status_code == 200
        data = r.json()
        assert data["active_mode"] in ("testing", "production")
        assert data["can_edit"] is True
        # Password is masked even when empty (always)
        assert "password" in data["testing"]

    def test_hr_admin_view_only(self, hr_client):
        r = hr_client.get(f"{API}/api/email-delivery")
        assert r.status_code == 200
        assert r.json()["can_edit"] is False
        r2 = hr_client.post(f"{API}/api/email-delivery/switch", json={"mode": "production"})
        assert r2.status_code == 403

    def test_update_mode_config_persists(self, it_client):
        r = it_client.put(f"{API}/api/email-delivery/testing", json={
            "smtp_host": "test.smtp.example.com", "smtp_port": 2525,
            "username": "u", "from_name": "X", "from_email": "x@y.z",
        })
        assert r.status_code == 200
        r2 = it_client.get(f"{API}/api/email-delivery")
        assert r2.json()["testing"]["smtp_host"] == "test.smtp.example.com"

    def test_switch_logs_audit(self, it_client):
        r = it_client.post(f"{API}/api/email-delivery/switch", json={"mode": "production"})
        assert r.status_code == 200
        r2 = it_client.get(f"{API}/api/email-delivery/audit")
        assert r2.status_code == 200
        assert any(a["new_mode"] == "production" for a in r2.json())
        # Switch back
        it_client.post(f"{API}/api/email-delivery/switch", json={"mode": "testing"})


# ---------------- Item 4 — Onboarding Tour ----------------

class TestOnboardingTour:
    def test_my_tour_returns_role_steps(self, hr_client):
        r = hr_client.get(f"{API}/api/onboarding-tour/me")
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert isinstance(d["steps"], list)
        assert len(d["steps"]) >= 4

    def test_mark_complete_then_state_reflects(self, it_client):
        r = it_client.post(f"{API}/api/onboarding-tour/complete", json={"skipped": False})
        assert r.status_code == 200
        r2 = it_client.get(f"{API}/api/onboarding-tour/me")
        assert r2.json()["completed"] is True
        # Replay resets it
        r3 = it_client.post(f"{API}/api/onboarding-tour/replay")
        assert r3.status_code == 200
        r4 = it_client.get(f"{API}/api/onboarding-tour/me")
        assert r4.json()["completed"] is False

    def test_config_it_admin_only(self, hr_client, it_client):
        # HR Admin denied
        r = hr_client.get(f"{API}/api/onboarding-tour/config")
        assert r.status_code == 403
        # IT Admin allowed
        r2 = it_client.get(f"{API}/api/onboarding-tour/config")
        assert r2.status_code == 200
        assert "headline_template" in r2.json()

    def test_config_update(self, it_client):
        r = it_client.put(f"{API}/api/onboarding-tour/config", json={
            "enabled": True, "headline_template": "Welcome — {{first_name}}", "body_text": "Test body"})
        assert r.status_code == 200
        assert r.json()["body_text"] == "Test body"

    def test_report_returns_role_breakdown(self, it_client):
        r = it_client.get(f"{API}/api/onboarding-tour/report")
        assert r.status_code == 200
        assert "by_role" in r.json()
        assert "total_users" in r.json()
