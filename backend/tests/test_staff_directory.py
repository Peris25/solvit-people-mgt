import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import employees
from utils.staff_directory import directory_departments, require_staff_directory
from utils.staff_views import build_staff_views
from utils.roster_reconciliation import reconcile_roster
from .integrity_fakes import Database, employee
from .test_staff_views import actor


@pytest.mark.parametrize("role", ["solver", "solvers_manager", "custom_staff", "", None])
def test_staff_contact_route_denies_non_staff_roles(role):
    db = Database([employee(employment_type="Full_Time")])
    with patch.object(employees, "get_current_user", AsyncMock(return_value=actor(role))), patch.object(employees, "get_db", return_value=db):
        for route in (employees.staff_directory, employees.employee_directory, employees.organogram):
            with pytest.raises(HTTPException) as error:
                asyncio.run(route(SimpleNamespace(query_params={"role": "hr_admin", "employee_id": "staff"})))
            assert error.value.status_code == 403
    assert db.employees.writes == db.system_settings.writes == 0


@pytest.mark.parametrize("employment", ["Full_Time", "full-time", "FTE"])
def test_linked_full_time_staff_can_read_contacts_and_source_notes(employment):
    db = Database([employee(employment_type=employment, department="IT Support", work_email="staff@solvit.co.ke")])
    with patch.object(employees, "get_current_user", AsyncMock(return_value=actor())), patch.object(employees, "get_db", return_value=db):
        result = asyncio.run(employees.staff_directory(SimpleNamespace()))
    assert len(result["employees"]) == 1
    assert result["employees"][0]["work_email"] == "staff@solvit.co.ke"
    assert "system access" in result["employees"][0]["contact_for"].lower()
    assert len(result["departments"]) == 6
    assert next(d for d in result["departments"] if d["name"] == "Operations")["contact_for"] == ""
    assert db.employees.writes == db.system_settings.writes == 0


@pytest.mark.parametrize("record", [None, employee(employment_type="Solver"), employee(employment_type="Contractor"),
                                      employee(), employee(employment_type="Full_Time", lifecycle_state="Exited")])
def test_unlinked_or_ineligible_employee_account_cannot_bypass_directory(record):
    db = Database([record] if record else [])
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_staff_directory(db, actor()))
    assert error.value.status_code == (409 if record is None else 403)


@pytest.mark.parametrize("role", ["hr_admin", "hr_manager", "finance", "line_manager", "executive", "it_admin", "board"])
def test_existing_authorized_staff_layers_keep_public_directory_access(role):
    asyncio.run(require_staff_directory(Database(), actor(role)))


@pytest.mark.parametrize("state", ["Candidate", "Suspended", "PIP", "Realignment", "Exited", "Unknown", ""])
def test_conservative_unknown_or_restricted_states_do_not_leak_to_public_views(state):
    record = employee("hidden", lifecycle_state=state, full_name="confidential-marker")
    directory, hierarchy = build_staff_views([record, employee(line_manager_id="hidden")], actor())
    assert "confidential-marker" not in json.dumps((directory, hierarchy))
    assert directory[0]["reporting_status"] == "unavailable"


def test_conflicting_legacy_exit_flag_and_restricted_self_remain_hidden():
    records = [employee("exited", lifecycle_state="Active", status="Exited"), employee(board_only=True)]
    assert build_staff_views(records, actor())[0] == []


@pytest.mark.parametrize("approval,expected", [(True, "+254 700 000 000"), (False, None), ("true", None), (None, None)])
def test_only_explicitly_approved_dedicated_work_phone_is_returned(approval, expected):
    record = employee(phone_number="private-marker", personal_email="private-marker", profile_photo_url="private-marker",
                      work_phone="+254 700 000 000", work_phone_directory_approved=approval, role_level="L3")
    original = deepcopy(record)
    directory, hierarchy = build_staff_views([record], actor())
    assert directory[0]["work_phone"] == expected
    assert "private-marker" not in json.dumps((directory, hierarchy))
    assert not set(("lifecycle_state", "role_level", "employment_type", "profile_photo_url")) & directory[0].keys()
    assert record == original


def test_invalid_phone_and_shared_email_pair_are_not_exposed_as_business_contacts():
    directory, _ = build_staff_views([employee(work_phone="https://private-marker", work_phone_directory_approved=True,
                                               work_email="one@example.com/two@example.com")], actor())
    assert directory[0]["work_phone"] is None and directory[0]["work_email"] is None


def test_master_purpose_overrides_and_unknown_departments_do_not_seed_or_rewrite():
    db = Database()
    db.system_settings.docs = [{"tenant_id": "solvit", "category": "workforce", "values": {"departments": [
        {"name": "IT Support", "contact_for": "Approved synthetic purpose"}, {"name": "Legacy", "contact_for": {"private": True}}]}}]
    data = asyncio.run(directory_departments(db, actor()))
    assert next(d for d in data if d["name"] == "IT Support")["contact_for"] == "Approved synthetic purpose"
    assert next(d for d in data if d["name"] == "Legacy")["contact_for"] == ""
    assert db.system_settings.writes == 0
    assert asyncio.run(directory_departments(Database(), actor(tenant="other"))) == []


def test_offline_reconciliation_flags_all_categories_without_pii_or_mutation():
    reference = [{"full_name": "Reference synthetic", "work_email": "reference@example.com", "department": "Operations", "role_title": "Coordinator"},
                 {"full_name": "Missing synthetic", "work_email": "missing@example.com", "department": "IT Support"}]
    records = [employee("duplicate", email="changed@example.com", full_name="Reference synthetic", department="Old", role_title="Old"),
               employee("duplicate", email="changed@example.com", full_name="Demo synthetic", department="Operations"),
               employee("left", full_name="Exited synthetic", lifecycle_state="Exited", department="Operations"),
               employee("old", full_name="Pending exit synthetic", department="Operations", line_manager_id="bad"),
               employee("foreign", tenant_id="other")]
    before = deepcopy(records)
    result = reconcile_roster(records, reference, ["Operations", "IT Support"], ["Demo synthetic"], ["Pending exit synthetic"])
    kinds = {i["kind"] for i in result["issues"]}
    assert {"duplicate_identifier", "duplicate_work_email", "missing_reference_record", "extra_record_requires_review",
            "demo_candidate_requires_review", "reference_exit_requires_review", "exited_record", "department_mismatch",
            "work_contact_email_mismatch", "title_mismatch", "unresolved_manager"} <= kinds
    assert result["snapshot_count"] == 4
    assert "synthetic" not in json.dumps(result).lower() and "@" not in json.dumps(result)
    assert records == before


def test_ambiguous_reference_matches_are_reported_not_chosen_or_merged():
    records = [employee("one", full_name="Synthetic duplicate"), employee("two", full_name="Synthetic duplicate")]
    result = reconcile_roster(records, [{"full_name": "Synthetic duplicate"}], [])
    assert {"ambiguous_roster_match", "potential_duplicate_name"} <= {i["kind"] for i in result["issues"]}
    assert result["read_only"] is True


def test_offline_extended_json_legacy_manager_alias_is_resolved_without_rewriting():
    oid = "abcdef012345abcdef012345"
    records = [{"_id": {"$oid": oid}, "id": "manager", "department": "Operations"},
               {"id": "staff", "line_manager_id": oid.upper(), "department": "Operations"}]
    result = reconcile_roster(records, [], ["Operations"])
    assert "unresolved_manager" not in {i["kind"] for i in result["issues"]}


def test_supplied_pdf_parsing_yields_reference_counts_without_embedded_roster():
    pytest.importorskip("pdfplumber", reason="Optional local reference-document review dependency")
    from pathlib import Path
    from scripts.reconcile_staff_roster import read_team_reference, read_brief_review_flags
    folder = Path(__file__).resolve().parents[2] / "docs" / "reference"
    if not (folder / "Solvit Team Directory - 2026.pdf").exists():
        pytest.skip("Confidential reference PDFs are provided locally, not published")
    reference = read_team_reference(folder / "Solvit Team Directory - 2026.pdf")
    demo, exited = read_brief_review_flags(next(folder.glob("*Developer Brief*v1.pdf")))
    assert len(reference) == 21 and len({r["department"] for r in reference}) == 6
    assert len(demo) == 8 and len(exited) == 1
    assert len({r["full_name"] for r in reference}) == 21


def test_offline_cli_never_overwrites_inputs_or_existing_reports(tmp_path):
    pytest.importorskip("pdfplumber", reason="Optional local reference-document review dependency")
    from pathlib import Path
    from scripts.reconcile_staff_roster import main
    folder = Path(__file__).resolve().parents[2] / "docs" / "reference"
    if not (folder / "Solvit Team Directory - 2026.pdf").exists():
        pytest.skip("Confidential reference PDFs are provided locally, not published")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps([{"id": "synthetic", "full_name": "Synthetic example", "tenant_id": "solvit"}]))
    output = tmp_path / "redacted-report.json"
    args = ["reconcile_staff_roster", "--snapshot", str(snapshot), "--reference-dir", str(folder), "--output"]
    original = snapshot.read_bytes()
    with patch("sys.argv", args + [str(output)]):
        main()
    saved = output.read_bytes()
    result = json.loads(saved)
    assert result["reference_count"] == 21 and result["snapshot_count"] == 1
    assert "Synthetic example" not in saved.decode() and "@" not in saved.decode()
    for target in (snapshot, output):
        with patch("sys.argv", args + [str(target)]), pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 1
    assert snapshot.read_bytes() == original and output.read_bytes() == saved


def test_public_source_projection_preserves_tenant_for_database_level_projection():
    from utils.staff_views import PUBLIC_SOURCE_FIELDS, read_staff_views
    from types import SimpleNamespace
    record = employee("foreign-staff", tenant_id="other")
    projected = {key: value for key, value in record.items() if key in PUBLIC_SOURCE_FIELDS}
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[projected]))
    db = SimpleNamespace(employees=SimpleNamespace(find=lambda *args: cursor),
                         system_settings=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    directory, _ = asyncio.run(read_staff_views(db, actor(tenant="other")))
    assert [entry["id"] for entry in directory] == ["foreign-staff"]
    assert "tenant_id" not in directory[0]
