from copy import deepcopy
import json
from pathlib import Path

import pytest
from utils.reporting_verification import expected_reporting, verify_reporting


def reference():
    return [
        {"full_name": "Synthetic MD", "role_title": "Managing Director", "department": "Leadership"},
        {"full_name": "Synthetic IT lead", "role_title": "IT Support", "department": "IT Support"},
        {"full_name": "Synthetic IT support", "role_title": "IT Support", "department": "IT Support"},
        {"full_name": "Synthetic technical", "role_title": "Technical Services Manager", "department": "Valuation"},
        {"full_name": "Synthetic valuer", "role_title": "Valuation Officer", "department": "Valuation"},
        {"full_name": "Synthetic operations", "role_title": "Operations Coordinator / Head of Solvers", "department": "Operations"},
    ]


def confirmations():
    return {"role_holders": {"IT Lead": "Synthetic IT lead", "Technical Services & Growth Manager": "Synthetic technical"},
            "title_overrides": {"Synthetic IT lead": "IT Lead"}}


def snapshot():
    employees = []
    for i, r in enumerate(reference()):
        employees.append({**r, "_id": f"storage-{i}", "id": f"canonical-{i}", "tenant_id": "solvit",
                          "employment_type": "Full-Time", "lifecycle_state": "Active"})
    employees[1].update(role_title="IT Lead", line_manager_id="canonical-0")
    employees[2]["line_manager_id"] = "storage-1"
    employees[3]["line_manager_id"] = "canonical-0"
    employees[4]["line_manager_id"] = "canonical-3"
    employees[5]["line_manager_id"] = "canonical-0"
    return employees


def test_confirmed_roles_resolve_named_reference_targets_without_changing_source():
    source = reference(); before = deepcopy(source)
    targets, head, _ = expected_reporting(source, confirmations())
    by_name = {r["full_name"]: r for r in targets}
    assert by_name["Synthetic IT support"]["manager_name"] == "Synthetic IT lead"
    assert by_name["Synthetic valuer"]["manager_name"] == "Synthetic technical"
    assert by_name["Synthetic technical"]["manager_name"] == "Synthetic MD"
    assert head["full_name"] == "Synthetic operations"
    assert source == before


def test_canonical_legacy_and_solver_manager_links_are_checked_read_only():
    employees = snapshot(); solvers = [{"_id": "s-storage", "id": "s-uuid", "full_name": "Synthetic solver", "line_manager_id": "storage-5"}]
    saved = deepcopy((employees, solvers))
    result = verify_reporting(employees, solvers, reference(), [{"full_name": "Synthetic solver"}], confirmations())
    rows = {r["reference_name"]: r for r in result["rows"]}
    assert rows["Synthetic IT support"]["verification_status"] == "matches_reference_proposal"
    assert rows["Synthetic valuer"]["current_manager"]["full_name"] == "Synthetic technical"
    assert rows["Synthetic solver"]["current_manager"]["role_title"].startswith("Operations Coordinator")
    assert (employees, solvers) == saved and result["read_only"] is True


@pytest.mark.parametrize("manager,issue", [(None, "missing_manager_assignment"), ("bad", "invalid_manager_reference"),
                                         ("canonical-1", "manager_differs_from_reference")])
def test_missing_invalid_and_conflicting_reporting_assignments_are_identified(manager, issue):
    employees = snapshot(); employees[4]["line_manager_id"] = manager
    result = verify_reporting(employees, [], reference(), [], confirmations())
    row = next(r for r in result["rows"] if r["reference_name"] == "Synthetic valuer")
    assert issue in row["issues"] and row["verification_status"] == "review_required"


def test_duplicate_canonical_manager_id_cannot_be_bypassed_by_unique_storage_alias():
    employees = snapshot();employees.append({**employees[3], "_id": "duplicate-storage"})
    employees[4]["line_manager_id"] = "storage-3"
    result = verify_reporting(employees, [], reference(), [], confirmations())
    row = next(r for r in result["rows"] if r["reference_name"] == "Synthetic valuer")
    assert "ambiguous_manager_reference" in row["issues"]


def test_cycles_exited_records_classification_and_department_errors_are_reported():
    employees = snapshot()
    employees[3]["line_manager_id"] = "canonical-4"
    employees[4].update(status="Exited", department="Wrong", employment_type="Solver")
    result = verify_reporting(employees, [], reference(), [], confirmations())
    row = next(r for r in result["rows"] if r["reference_name"] == "Synthetic valuer")
    assert {"reporting_cycle", "reference_member_is_exited", "department_mismatch", "employment_classification_needs_review"} <= set(row["issues"])


def test_foreign_managers_extras_and_missing_reference_records_never_trigger_creation():
    employees = snapshot();employees[3]["tenant_id"] = "foreign"
    employees.append({"id": "extra", "_id": "extra-store", "full_name": "Extra synthetic"})
    result = verify_reporting(employees, [], reference(), [{"full_name": "Missing synthetic solver"}], confirmations())
    assert result["extra_employee_labels"] and result["snapshot_counts"]["employees"] == 6
    assert "missing_reference_record" in result["rows"][-1]["issues"]


def test_unconfirmed_it_role_is_not_inferred_from_title_or_department():
    targets, _, warnings = expected_reporting(reference(), {})
    assert any(r["role"] == "IT Lead" for r in warnings)
    assert next(r for r in targets if r["full_name"] == "Synthetic IT support")["manager_name"] is None


def test_snapshot_private_fields_and_malformed_public_metadata_are_not_reported():
    employees = snapshot();employees[3].update(bank_account="private-marker", medical_notes="private-marker", department={"salary": "private-marker"})
    result = verify_reporting(employees, [], reference(), [], confirmations())
    assert "private-marker" not in json.dumps(result)


def test_supplied_solver_document_parses_actual_rows_instead_of_inventing_118_people():
    pytest.importorskip("pdfplumber")
    from scripts.verify_workforce_reporting import read_solver_reference
    path = Path(__file__).resolve().parents[2] / "docs/reference/Solvit Solver Directory - September 2026.pdf"
    if not path.exists(): pytest.skip("Confidential local reference document is not published")
    rows = read_solver_reference(path)
    assert len(rows) == 109 and len({r["full_name"] for r in rows}) == 109
    assert sum(not r["phone_present"] for r in rows) == 1
    assert all("phone" not in r for r in rows)
