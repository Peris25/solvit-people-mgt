"""Reference roster imports preserve unknown facts and existing Solvers."""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from openpyxl import Workbook

from routes import data_import
from .integrity_fakes import Collection, Database


def row(**overrides):
    values = {"Full Name": "Reference Solver", "Phone Number": "+254711222333", "App Status": "Active"}
    values.update(overrides)
    return [values.get(name) for name, _ in data_import.TEMPLATES["solver"]["columns"]]


def database():
    db = Database()
    db.solvers = Collection([{"_id": ObjectId(), "id": "existing", "tenant_id": "solvit", "phone_number": "+254722333444", "lifecycle_state": "Inactive"}])
    db.data_import_log = Collection()
    return db


@pytest.mark.parametrize("overrides,valid", [
    ({}, True),
    ({"Date of Onboarding": "not-a-date"}, False),
    ({"App Status": None}, False),
    ({"Phone Number": "0722333444"}, False),
])
def test_reference_validation(overrides, valid):
    result = asyncio.run(data_import._validate_rows("solver", [row(**overrides)], database()))
    assert result[0]["valid"] is valid


def test_duplicate_phone_within_batch():
    result = asyncio.run(data_import._validate_rows("solver", [row(), row(**{"Phone Number": "0711222333"})], database()))
    assert result[0]["valid"]
    assert not result[1]["valid"]


def test_original_template_columns_remain_compatible():
    legacy_row = row(**{"Date of Onboarding": "10/01/2026"})[:14]
    result = asyncio.run(data_import._validate_rows("solver", [legacy_row], database()))
    assert result[0]["valid"]
    assert result[0]["normalized"]["Date of Onboarding"] == "2026-01-10"
    assert result[0]["normalized"]["Region"] is None


def test_import_preserves_unknowns_and_existing_inactive_solver(tmp_path, monkeypatch):
    db = database()
    wb = Workbook()
    wb.active.title = "Data"
    wb.active.append([name for name, _ in data_import.TEMPLATES["solver"]["columns"]])
    wb.active.append(row(**{"Region": "Coast", "Area Covered": "Reference coverage"}))
    content = io.BytesIO()
    wb.save(content)
    (tmp_path / "reference.xlsx").write_bytes(content.getvalue())
    monkeypatch.setattr(data_import, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(data_import, "get_db", lambda: db)
    monkeypatch.setattr(data_import, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin", "tenant_id": "solvit"}))
    monkeypatch.setattr(data_import, "solver_access", AsyncMock())
    request = SimpleNamespace(json=AsyncMock(return_value={"kind": "solver", "cache_id": "reference"}))
    result = asyncio.run(data_import.execute_import(request))
    assert result["imported"] == 1
    docs = asyncio.run(db.solvers.find({}).to_list(None))
    existing = next(d for d in docs if d["id"] == "existing")
    imported = next(d for d in docs if d["id"] != "existing")
    assert existing["lifecycle_state"] == "Inactive"
    assert imported["lifecycle_state"] == "Active"
    assert imported["region"] == "Coast"
    assert imported["area_covered"] == "Reference coverage"
    for field in ("onboarded_at", "jobs_completed", "accuracy_score", "client_rating_average"):
        assert imported[field] is None
    repeated = asyncio.run(data_import.execute_import(request))
    assert repeated["imported"] == 0
    assert repeated["skipped"] == 1
