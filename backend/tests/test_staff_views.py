import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from routes import employees
from utils.employee_integrity import find_employee, resolve_user_employee
from utils.staff_views import build_staff_views, read_staff_views, MAX_TREE_DEPTH
from utils.staff_directory import employment_type
from .integrity_fakes import Database, employee, account


def actor(role="employee", employee_id="staff", tenant="solvit"):
    return {"id": "synthetic-user", "role": role, "employee_id": employee_id, "tenant_id": tenant}


def flatten(hierarchy):
    pending = list(hierarchy["roots"])
    out = []
    while pending:
        node = pending.pop()
        out.append(node)
        pending.extend(node["direct_reports"])
    assert len({node["node_id"] for node in out}) == len(out)
    assert len(out) == hierarchy["total"]
    return out


@pytest.mark.parametrize("reference", ["canonical", "legacy-string", "legacy-object"])
def test_manager_aliases_resolve_without_changing_records(reference):
    boss = employee("boss", full_name="Synthetic manager")
    manager_id = "boss" if reference == "canonical" else str(boss["_id"]) if reference == "legacy-string" else boss["_id"]
    staff = employee(line_manager_id=manager_id)
    records = [boss, staff]
    saved = deepcopy(records)
    directory, hierarchy = build_staff_views(records, actor())
    assert next(e for e in directory if e["id"] == "staff")["line_manager_name"] == "Synthetic manager"
    assert hierarchy["roots"][0]["direct_reports"][0]["id"] == "staff"
    assert records == saved


def test_missing_uuid_and_objectid_uuid_are_supported_by_canonical_lookup():
    legacy = employee()
    legacy.pop("id")
    typed = employee(ObjectId())
    db = Database([legacy, typed])
    for record in (legacy, typed):
        reference = record.get("id", record["_id"])
        assert asyncio.run(find_employee(db, reference))["_id"] == record["_id"]
    directory, hierarchy = build_staff_views([legacy, typed], actor(employee_id=str(legacy["_id"])))
    assert {e["id"] for e in directory} == {str(legacy["_id"]), str(typed["id"])}
    assert len(flatten(hierarchy)) == 2


def test_string_mongo_identity_is_resolved():
    record = employee()
    record.pop("id")
    record["_id"] = "legacy-storage-identity"
    assert asyncio.run(find_employee(Database([record]), record["_id"]))["_id"] == record["_id"]


@pytest.mark.parametrize("manager,status", [(None, "none"), ("invalid", "unavailable"), ({"salary": "restricted-marker"}, "unavailable")])
def test_unresolved_managers_do_not_hide_staff_or_leak_raw_references(manager, status):
    directory, hierarchy = build_staff_views([employee(line_manager_id=manager)], actor())
    assert hierarchy["total"] == len(flatten(hierarchy)) == 1
    assert directory[0]["reporting_status"] == status and directory[0]["line_manager_id"] is None
    assert "restricted-marker" not in json.dumps(hierarchy)


def test_duplicate_ids_preserve_nodes_and_never_choose_a_manager():
    first, second = employee("duplicate"), employee("duplicate")
    child = employee("child", line_manager_id="duplicate")
    records = [first, second, child]
    directory, hierarchy = build_staff_views(records, actor(employee_id="child"))
    assert len(flatten(hierarchy)) == 3
    assert len({e["node_id"] for e in directory}) == len({e["id"] for e in directory}) == 3
    assert sum(e["identity_status"] == "ambiguous" for e in directory) == 2
    assert next(e for e in directory if e["id"] == "child")["reporting_status"] == "ambiguous"
    with pytest.raises(HTTPException) as error:
        asyncio.run(find_employee(Database(records), "duplicate"))
    assert error.value.status_code == 409


def test_storage_alias_cannot_bypass_ambiguous_canonical_account_identity():
    first, second = employee("duplicate"), employee("duplicate", "other@example.com")
    user = account(employee_id=str(first["_id"]))
    with pytest.raises(HTTPException) as error:
        asyncio.run(resolve_user_employee(Database([first, second], [user]), user))
    assert error.value.status_code == 409


def test_cross_alias_collision_is_ambiguous_in_both_views_and_lookup():
    first = employee("first")
    second = employee(str(first["_id"]))
    child = employee("child", line_manager_id=str(first["_id"]))
    records = [first, second, child]
    directory, hierarchy = build_staff_views(records, actor(employee_id="child"))
    assert len(flatten(hierarchy)) == 3
    assert next(e for e in directory if e["id"] == "child")["reporting_status"] == "ambiguous"
    with pytest.raises(HTTPException):
        asyncio.run(find_employee(Database(records), str(first["_id"])))


@pytest.mark.parametrize("length", [1, 2, 4])
def test_cycles_are_cut_for_presentation_and_every_record_remains_visible(length):
    records = [employee(f"cycle-{i}", line_manager_id=f"cycle-{(i+1)%length}") for i in range(length)]
    records.append(employee("outside", line_manager_id="cycle-0"))
    saved = deepcopy(records)
    directory, hierarchy = build_staff_views(records, actor(employee_id="outside"))
    assert len(flatten(hierarchy)) == length + 1
    assert sum(e["reporting_status"] == "cycle" for e in directory) == length
    assert records == saved
    json.dumps(hierarchy)


def test_deep_chain_is_bounded_without_losing_nodes():
    records = [employee(f"staff-{i}", line_manager_id=f"staff-{i-1}" if i else None) for i in range(150)]
    _, hierarchy = build_staff_views(records, actor(employee_id="staff-0"))
    assert len(flatten(hierarchy)) == 150
    pending = [(root, 0) for root in hierarchy["roots"]]
    while pending:
        node, depth = pending.pop()
        assert depth <= MAX_TREE_DEPTH
        pending.extend((child, depth + 1) for child in node["direct_reports"])
    json.dumps(hierarchy)


@pytest.mark.parametrize("field,value", [("lifecycle_state", " Exited "), ("status", "exited"), ("employment_status", "EXITED")])
def test_exited_formats_are_excluded_and_their_reports_have_no_hidden_manager_details(field, value):
    boss = employee("boss", full_name="restricted-marker")
    boss.pop("lifecycle_state")
    boss[field] = value
    staff = employee(line_manager_id="boss")
    directory, hierarchy = build_staff_views([boss, staff], actor())
    assert len(directory) == hierarchy["total"] == 1
    assert directory[0]["reporting_status"] == "unavailable"
    assert "restricted-marker" not in json.dumps(hierarchy)
    assert directory[0]["line_manager_id"] is None


@pytest.mark.parametrize("role,own,expected", [("employee", "staff", 1), ("hr_admin", "staff", 1),
    ("finance", "staff", 1), ("line_manager", "staff", 1), ("custom_staff", "staff", 1),
    ("board", "staff", 2), ("it_admin", "staff", 2), ("executive", "boss", 1)])
def test_directory_and_hierarchy_have_identical_board_visibility(role, own, expected):
    boss = employee("boss", board_only=True, full_name="restricted-marker")
    staff = employee(line_manager_id="boss")
    directory, hierarchy = build_staff_views([boss, staff], actor(role, own))
    assert len(directory) == len(flatten(hierarchy)) == expected
    assert {e["node_id"] for e in directory} == {e["node_id"] for e in flatten(hierarchy)}
    if expected == 1:
        assert "restricted-marker" not in json.dumps((directory, hierarchy))
        assert directory[0]["line_manager_id"] is None


def test_hidden_duplicate_is_not_silently_selected_as_visible_manager():
    records = [employee("duplicate"), employee("duplicate", board_only=True), employee(line_manager_id="duplicate")]
    directory, hierarchy = build_staff_views(records, actor())
    assert len(flatten(hierarchy)) == 2
    assert next(e for e in directory if e["id"] == "staff")["reporting_status"] == "ambiguous"


@pytest.mark.parametrize("saved,normalized", [("FTE", "Full_Time"), ("Full-Time", "Full_Time"),
    ("full_time", "Full_Time"), ("Part Time", "Part_Time"), ("Fixed-Term", "Fixed_Term"),
    ("Contractor", "Contractor"), ("Consultant", "Consultant"), ("Legacy special type", "Legacy special type")])
def test_display_compatibility_does_not_reclassify_or_rewrite_departments_and_employment(saved, normalized):
    record = employee(department="HR_People", employment_type=saved, job_level=" l3 ", lifecycle_state="on leave")
    before = deepcopy(record)
    directory, _ = build_staff_views([record], actor(), ["Operations", "HR & People"])
    node = directory[0]
    assert node["department"] == "HR_People" and node["department_label"] == "HR & People"
    assert employment_type(record["employment_type"]) == normalized
    assert not any(field in node for field in ("employment_type", "role_level", "lifecycle_state"))
    assert record == before


def test_unknown_and_ambiguous_department_labels_are_preserved():
    for department, configured in [("Legacy Department", ["Operations"]), ("RD", ["R&D", "R D"])]:
        directory, _ = build_staff_views([employee(department=department)], actor(), configured)
        assert directory[0]["department_label"] == department


def test_sensitive_fields_and_nested_public_values_are_never_returned():
    record = employee(current_salary_kes="restricted-marker", salary_kes="restricted-marker", bank_account="restricted-marker",
                      medical_details="restricted-marker", disciplinary_cases="restricted-marker", national_id="restricted-marker",
                      kra_pin="restricted-marker", phone_number="restricted-marker", personal_email="restricted-marker",
                      date_of_birth="restricted-marker", flags={"restricted-marker": True}, department={"bank": "restricted-marker"})
    for role in ("employee", "hr_admin", "board"):
        directory, hierarchy = build_staff_views([record], actor(role))
        assert "restricted-marker" not in json.dumps((directory, hierarchy))
        assert not any(key in directory[0] for key in ("salary_kes", "current_salary_kes", "bank_account", "medical_details", "disciplinary_cases"))


def test_malformed_composite_identifiers_are_not_exposed_or_selected():
    record = employee({"bank": "restricted-marker"})
    record["_id"] = {"private": "restricted-marker"}
    directory, hierarchy = build_staff_views([record], actor())
    assert directory[0]["id"] is None
    assert "restricted-marker" not in json.dumps((directory, hierarchy))


def test_scoped_legacy_tenants_and_read_only_master_labels():
    records = [employee(), employee("legacy"), employee("foreign", tenant_id="other")]
    records[1].pop("tenant_id")
    db = Database(records)
    db.system_settings.docs = [{"tenant_id": "solvit", "category": "workforce", "values": {"departments": [{"name": "HR & People"}]}}]
    for role in ("employee", "board"):
        directory, hierarchy = asyncio.run(read_staff_views(db, actor(role)))
        assert {e["id"] for e in directory} == {"staff", "legacy"}
        assert len(flatten(hierarchy)) == 2
    assert db.employees.writes == db.system_settings.writes == 0
    other, _ = asyncio.run(read_staff_views(db, actor(tenant="other")))
    assert [e["id"] for e in other] == ["foreign"]


@pytest.mark.parametrize("values", [None, "invalid", {"departments": None}, {"departments": "invalid"}])
def test_invalid_master_formats_preserve_saved_departments_without_writes(values):
    db = Database([employee(department="Saved Legacy Department")])
    db.system_settings.docs = [{"tenant_id": "solvit", "category": "workforce", "values": values}]
    directory, _ = asyncio.run(read_staff_views(db, actor()))
    assert directory[0]["department_label"] == "Saved Legacy Department"
    assert db.system_settings.writes == 0


def test_both_routes_authenticate_and_use_the_same_read_only_projection():
    db = Database([employee(employment_type="Full_Time")])
    with patch.object(employees, "get_current_user", AsyncMock(return_value=actor())), patch.object(employees, "get_db", return_value=db):
        directory = asyncio.run(employees.employee_directory(SimpleNamespace()))
        hierarchy = asyncio.run(employees.organogram(SimpleNamespace()))
    assert len(directory) == hierarchy["total"] == 1
    assert db.employees.writes == db.system_settings.writes == 0


def test_task01_manager_display_does_not_guess_ambiguous_names():
    db = Database([employee("duplicate", full_name="First synthetic manager"), employee("duplicate", full_name="Second synthetic manager")])
    assert asyncio.run(employees._line_manager_name(db, "duplicate")) is None
