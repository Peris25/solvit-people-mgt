"""Directory lookup cost stays constant without weakening identity checks."""
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from routes import solvers
from utils.solver_access import find_solver, validate_directory_identities, solver_key
from .test_solver_security import actor, database, run, solver


@pytest.mark.parametrize("size", [1, 108, 500])
def test_directory_uses_one_solver_query_regardless_of_roster_size(size):
    records = [solver(str(i)) for i in range(size)]
    db = database(records)
    before = deepcopy(db.solvers.docs)
    with patch.object(solvers.workflow, "directory_access", AsyncMock(return_value={"scope": "all"})), \
            patch.object(db.solvers, "find", wraps=db.solvers.find) as reads:
        _, result = run(solvers.directory_records(db, actor()))
    assert len(result) == size
    assert reads.call_count == 1
    assert db.solvers.docs == before
    assert db.solvers.writes == 0


@pytest.mark.parametrize("case", ["legacy", "native_id", "duplicate", "storage_collision", "uppercase_collision"])
def test_batch_validation_matches_single_record_resolution(case):
    first = solver("one")
    second = solver("two")
    if case == "legacy": first.pop("id")
    if case == "native_id": first["id"] = ObjectId()
    if case == "duplicate": second["id"] = first["id"]
    if case == "storage_collision": second["id"] = str(first["_id"]); first.pop("id")
    if case == "uppercase_collision": second["id"] = str(first["_id"]).upper(); first.pop("id")
    records = [first, second]
    db = database(records)
    failed = False
    for record in records:
        try:
            run(find_solver(db, solver_key(record), actor()))
        except HTTPException:
            failed = True
    if failed:
        with pytest.raises(HTTPException) as error:
            validate_directory_identities(records)
        assert error.value.status_code == 409
    else:
        validate_directory_identities(records)


def test_foreign_tenant_alias_does_not_poison_directory():
    db = database([solver(), solver(tenant_id="other")])
    with patch.object(solvers.workflow, "directory_access", AsyncMock(return_value={"scope": "all"})):
        _, result = run(solvers.directory_records(db, actor()))
    assert len(result) == 1
    assert result[0]["tenant_id"] == "solvit"


def test_own_scope_keeps_checks_outside_visible_record():
    db = database([solver(), solver(email="different@example.test")])
    with patch.object(solvers.workflow, "directory_access", AsyncMock(return_value={"scope": "own_record"})):
        with pytest.raises(HTTPException) as error:
            run(solvers.directory_records(db, actor("solver", solver_id="one")))
    assert error.value.status_code == 409
