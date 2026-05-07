"""Iteration 7 — Board role, MD/ED Board-only, MD KPIs, Settings-driven leave/probation/PAYE,
CSV exports, AccessGate hooks, FOM combined role + reporting chain."""
import os
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://solvit-people-mgmt.preview.emergentagent.com").rstrip("/")
PWD = "Solvit@2026"


def _login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def board():
    return _login("board@solvit.co.ke")


@pytest.fixture(scope="module")
def hr():
    s = _login("jessica@solvit.co.ke")
    return s


@pytest.fixture(scope="module", autouse=True)
def _reset_demo():
    """Reset demo data ONCE before all tests so IDs stay stable."""
    s = _login("jessica@solvit.co.ke")
    s.post(f"{BASE_URL}/api/settings/reset-demo-data", timeout=60)
    yield


@pytest.fixture(scope="module")
def employee():
    return _login("employee@solvit.co.ke")


@pytest.fixture(scope="module")
def it_admin():
    return _login("itadmin@solvit.co.ke")


@pytest.fixture(scope="module")
def finance():
    return _login("finance@solvit.co.ke")


@pytest.fixture(scope="module")
def md():
    return _login("md@solvit.co.ke")


# ---------- Auth / Board role ----------
class TestBoardAuth:
    def test_board_login_role(self, board):
        me = board.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200
        data = me.json()
        assert data["role"] == "board"
        assert data["email"] == "board@solvit.co.ke"


# ---------- Employees scoping (Board sees MD/ED, HR Admin does not) ----------
class TestEmployeeBoardScoping:
    def test_board_sees_md_and_ed(self, board):
        r = board.get(f"{BASE_URL}/api/employees", timeout=20)
        assert r.status_code == 200
        emps = r.json()
        names = [e.get("full_name", "") for e in emps]
        assert any("Michael Omondi" in n for n in names), f"MD missing: {names}"
        assert any("Esther Wanjala" in n for n in names), f"ED missing: {names}"
        # store ids on the test class
        TestEmployeeBoardScoping.md_id = next(e["id"] for e in emps if "Michael Omondi" in e.get("full_name", ""))
        TestEmployeeBoardScoping.ed_id = next(e["id"] for e in emps if "Esther Wanjala" in e.get("full_name", ""))
        TestEmployeeBoardScoping.board_count = len(emps)
        assert len(emps) >= 13, f"expected >=13 employees as Board, got {len(emps)}"

    def test_hr_admin_hides_md_and_ed(self, hr):
        r = hr.get(f"{BASE_URL}/api/employees", timeout=20)
        assert r.status_code == 200
        emps = r.json()
        names = [e.get("full_name", "") for e in emps]
        assert not any("Michael Omondi" in n for n in names), "MD must be hidden from HR Admin"
        assert not any("Esther Wanjala" in n for n in names), "ED must be hidden from HR Admin"
        TestEmployeeBoardScoping.hr_count = len(emps)
        assert len(emps) <= TestEmployeeBoardScoping.board_count - 2

    def test_hr_get_md_403(self, hr):
        md_id = TestEmployeeBoardScoping.md_id
        r = hr.get(f"{BASE_URL}/api/employees/{md_id}", timeout=15)
        assert r.status_code == 403
        detail = (r.json().get("detail") or "").lower()
        assert "board" in detail

    def test_hr_get_ed_403(self, hr):
        ed_id = TestEmployeeBoardScoping.ed_id
        r = hr.get(f"{BASE_URL}/api/employees/{ed_id}", timeout=15)
        assert r.status_code == 403

    def test_board_get_md_200(self, board):
        md_id = TestEmployeeBoardScoping.md_id
        r = board.get(f"{BASE_URL}/api/employees/{md_id}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "Michael Omondi" in data.get("full_name", "")


# ---------- Review panel routing (MD, ED, FOM-direct, FOM-report) ----------
class TestReviewPanel:
    def test_md_panel_board_led(self, board):
        md_id = TestEmployeeBoardScoping.md_id
        r = board.get(f"{BASE_URL}/api/performance/review-panel/{md_id}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("panel_type") == "board_led"
        assert data.get("panel") == []
        assert data.get("casting_vote_role") == "board_chair"

    def test_ed_panel_board_led(self, board):
        ed_id = TestEmployeeBoardScoping.ed_id
        r = board.get(f"{BASE_URL}/api/performance/review-panel/{ed_id}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("panel_type") == "board_led"
        note = (data.get("note") or "").lower()
        assert "executive director" in note or "ed" in note

    def test_sarah_md_direct_report_panel(self, hr, board):
        # find Sarah's id
        emps = hr.get(f"{BASE_URL}/api/employees", timeout=20).json()
        sarah = next((e for e in emps if "Sarah Njoroge" in e.get("full_name", "")), None)
        assert sarah, "Sarah Njoroge missing"
        sid = sarah["id"]
        r = board.get(f"{BASE_URL}/api/performance/review-panel/{sid}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("panel_type") == "md_direct_report"
        roles = [p.get("role") for p in data.get("panel", [])]
        assert "md" in roles and "hr_admin" in roles, roles

    def test_grace_solvers_mgr_finance_ops_report(self, hr, board):
        emps = board.get(f"{BASE_URL}/api/employees", timeout=20).json()
        grace = next((e for e in emps if "Grace Akinyi" in e.get("full_name", "")), None)
        assert grace, "Grace Akinyi missing"
        gid = grace["id"]
        r = board.get(f"{BASE_URL}/api/performance/review-panel/{gid}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("panel_type") == "finance_ops_report"
        roles = [p.get("role") for p in data.get("panel", [])]
        assert "hr_admin" in roles
        # line_manager:finance_ops or similar
        lm_entry = next((p for p in data.get("panel", []) if p.get("role", "").startswith("line_manager")), None)
        assert lm_entry is not None, data


# ---------- MD KPIs (Board + Executive only) ----------
class TestMdKpis:
    def test_board_can_read(self, board):
        r = board.get(f"{BASE_URL}/api/performance/md-kpis", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        kpis = data.get("kpis") if isinstance(data, dict) else data
        assert isinstance(kpis, list), data
        assert len(kpis) == 8, f"expected 8 KPIs, got {len(kpis)}"
        names = " ".join((k.get("kpi") or k.get("name") or k.get("title") or "") for k in kpis).lower()
        for token in ["revenue growth", "alignment survey", "operational kpi", "budget adherence",
                      "client retention", "csat", "channel partner nps", "board reporting"]:
            assert token in names, f"missing KPI token: {token} | names={names}"

    def test_hr_403(self, hr):
        r = hr.get(f"{BASE_URL}/api/performance/md-kpis", timeout=15)
        assert r.status_code == 403


# ---------- Demo data: roles ----------
class TestDemoDataRoles:
    def test_sarah_finance_ops_mgr(self, hr):
        emps = hr.get(f"{BASE_URL}/api/employees", timeout=20).json()
        sarah = next((e for e in emps if "Sarah Njoroge" in e.get("full_name", "")), None)
        assert sarah, "Sarah missing"
        assert sarah.get("role_title") == "Finance & Operations Manager", sarah.get("role_title")

    def test_lillian_growth_captain(self, hr):
        emps = hr.get(f"{BASE_URL}/api/employees", timeout=20).json()
        lillian = next((e for e in emps if "Lillian Achieng" in e.get("full_name", "")), None)
        assert lillian, "Lillian Achieng missing"
        assert lillian.get("role_title") == "Growth Captain", lillian.get("role_title")

    def test_daniel_tech_services_mgr(self, hr):
        emps = hr.get(f"{BASE_URL}/api/employees", timeout=20).json()
        dan = next((e for e in emps if "Daniel Mutua" in e.get("full_name", "")), None)
        assert dan, "Daniel Mutua missing"
        assert dan.get("role_title") == "Technical Services Manager", dan.get("role_title")


# ---------- Settings-driven leave types ----------
class TestLeaveTypesSettings:
    def test_default_leave_types(self, it_admin, hr):
        # Reset lookups to defaults via IT Admin
        rr = it_admin.post(f"{BASE_URL}/api/settings/masters/lookups/reset", timeout=15)
        assert rr.status_code in (200, 204), rr.text
        r = hr.get(f"{BASE_URL}/api/leave/types", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Response is a dict keyed by leave-type name OR list
        if isinstance(data, dict) and not any(k in data for k in ("leave_types", "types")):
            names = list(data.keys())
        elif isinstance(data, dict):
            tlist = data.get("leave_types") or data.get("types") or []
            names = [t if isinstance(t, str) else (t.get("name") or t.get("type")) for t in tlist]
        else:
            names = [t if isinstance(t, str) else (t.get("name") or t.get("type")) for t in data]
        for x in ["Annual", "Sick", "Maternity", "Paternity", "Compassionate", "Unpaid"]:
            assert x in names, f"missing default {x}: {names}"

    def test_remove_compassionate(self, it_admin, hr):
        cur = it_admin.get(f"{BASE_URL}/api/settings/masters/lookups", timeout=15).json()
        values = cur.get("values") if isinstance(cur, dict) and "values" in cur else cur
        leave_types = values.get("leave_types")
        assert isinstance(leave_types, list)
        new_leave = [lt for lt in leave_types if (lt if isinstance(lt, str) else lt.get("name")) != "Compassionate"]
        values["leave_types"] = new_leave
        upd = it_admin.put(f"{BASE_URL}/api/settings/masters/lookups", json={"values": values}, timeout=15)
        assert upd.status_code == 200, upd.text
        r = hr.get(f"{BASE_URL}/api/leave/types", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, dict) and not any(k in data for k in ("leave_types", "types")):
            names = list(data.keys())
        else:
            tlist = data if isinstance(data, list) else (data.get("leave_types") or data.get("types") or [])
            names = [t if isinstance(t, str) else (t.get("name") or t.get("type")) for t in tlist]
        assert "Compassionate" not in names, names
        # restore
        it_admin.post(f"{BASE_URL}/api/settings/masters/lookups/reset", timeout=15)


# ---------- Probation period from settings ----------
class TestProbationFromSettings:
    def _create(self, hr, suffix: str, start_date: str):
        body = {
            "full_name": f"TEST_iter7_{suffix}",
            "work_email": f"test_iter7_{suffix}@solvit.co.ke",
            "department": "Operations",
            "role_title": "Tester",
            "role_level": "L2",
            "start_date": start_date,
            "employment_type": "Full_Time",
        }
        r = hr.post(f"{BASE_URL}/api/employees", json=body, timeout=20)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_default_3_months(self, hr, it_admin):
        # ensure default
        it_admin.post(f"{BASE_URL}/api/settings/masters/organisation/reset", timeout=15)
        emp = self._create(hr, "probA", "2026-01-15")
        probation_end = emp.get("probation_end_date", "")
        assert probation_end.startswith("2026-04"), f"expected 2026-04..., got {probation_end}"
        TestProbationFromSettings.id_a = emp["id"]

    def test_changed_to_6_months(self, hr, it_admin):
        cur = it_admin.get(f"{BASE_URL}/api/settings/masters/organisation", timeout=15).json()
        values = cur.get("values") if isinstance(cur, dict) and "values" in cur else cur
        values["probation_period_months"] = 6
        upd = it_admin.put(f"{BASE_URL}/api/settings/masters/organisation", json={"values": values}, timeout=15)
        assert upd.status_code == 200, upd.text
        emp = self._create(hr, "probB", "2026-01-15")
        probation_end = emp.get("probation_end_date", "")
        assert probation_end.startswith("2026-07"), f"expected 2026-07..., got {probation_end}"
        TestProbationFromSettings.id_b = emp["id"]
        # restore default
        it_admin.post(f"{BASE_URL}/api/settings/masters/organisation/reset", timeout=15)

    def test_cleanup(self, hr):
        for attr in ("id_a", "id_b"):
            i = getattr(TestProbationFromSettings, attr, None)
            if i:
                hr.delete(f"{BASE_URL}/api/employees/{i}", timeout=15)


# ---------- PAYE calculator pulls from settings ----------
class TestPayeCalculator:
    def test_paye_calc(self, hr):
        r = hr.get(f"{BASE_URL}/api/compliance/paye-calculator", params={"gross_salary": 50000}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "paye_kes" in data
        assert "nssf_employee_kes" in data
        assert "sha_kes" in data
        assert data.get("config_source", "").startswith("masters_settings")


# ---------- Exports CSV ----------
class TestExports:
    def test_employees_csv_hr(self, hr):
        r = hr.get(f"{BASE_URL}/api/exports/employees.csv", timeout=20)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "filename=" in cd and ".csv" in cd

    def test_employees_csv_employee_403(self, employee):
        r = employee.get(f"{BASE_URL}/api/exports/employees.csv", timeout=20)
        assert r.status_code == 403

    def test_pay_bands_csv(self, hr):
        r = hr.get(f"{BASE_URL}/api/exports/pay-bands.csv", timeout=20)
        assert r.status_code == 200, r.text
        text = r.text
        assert "band" in text.lower()
        # Should contain min/mid/max columns
        first = text.split("\n", 1)[0].lower()
        assert "min_kes" in first and "mid_kes" in first and "max_kes" in first

    def test_budget_allocations_csv(self, hr):
        r = hr.get(f"{BASE_URL}/api/exports/budget-allocations.csv", timeout=20)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")


# ---------- Form 28 wording ----------
class TestForm28:
    def test_hr_blocked_with_finance_ops_wording(self, hr):
        # find any allocation id
        allocs = hr.get(f"{BASE_URL}/api/budget/allocations", timeout=15)
        if allocs.status_code == 200 and isinstance(allocs.json(), list) and allocs.json():
            aid = allocs.json()[0].get("id") or allocs.json()[0].get("_id")
        else:
            aid = "any"
        r = hr.post(f"{BASE_URL}/api/budget/form-28", json={"allocation_id": aid, "tier_confirmation": "T1"}, timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "finance & operations manager" in detail or "finance and operations manager" in detail, detail


# ---------- Regression ----------
class TestRegression:
    def test_access_matrix(self, hr):
        r = hr.get(f"{BASE_URL}/api/access/matrix", timeout=15)
        assert r.status_code == 200

    def test_settings_masters(self, hr):
        r = hr.get(f"{BASE_URL}/api/settings/masters", timeout=15)
        assert r.status_code == 200

    def test_budget_envelope(self, hr):
        r = hr.get(f"{BASE_URL}/api/budget/envelope", timeout=15)
        assert r.status_code == 200
