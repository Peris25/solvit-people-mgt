"""Pure chart/reference/snapshot comparison; never creates or modifies records."""
from collections import defaultdict
from utils.roster_reconciliation import clean, reference_key

ROLE_TITLES = {
    "Managing Director": {"managingdirector"},
    "Executive Director": {"executivedirector"},
    "Finance & Operations Manager": {"financeoperationsmanager"},
    "Technical Services & Growth Manager": {"technicalservicesgrowthmanager"},
    "Growth Captain": {"growthcaptain", "businessdevelopmentmanagergrowthcaptain"},
    "Operations Coordinator": {"operationscoordinator", "operationscoordinatorheadofsolvers"},
    "Human Resource & Administration Manager": {"humanresourceadministrationmanager", "hradministrationmanager"},
    "IT Lead": {"itlead"},
}
TEAM_MANAGERS = {"Account Management": "Finance & Operations Manager",
                 "Valuation": "Technical Services & Growth Manager", "IT Support": "IT Lead"}


def token(value):
    return "".join(c for c in clean(value) if c.isalnum())


def text(value):
    return value if isinstance(value, str) else None


def expected_reporting(reference, confirmations):
    """Named holders come from documents and a separate local HR confirmation file."""
    holders, warnings = {}, []
    confirmed = confirmations.get("role_holders", {})
    for role, variants in ROLE_TITLES.items():
        chosen = confirmed.get(role)
        candidates = [r for r in reference if clean(r.get("full_name")) == clean(chosen)] if chosen else [
            r for r in reference if token(r.get("role_title")) in variants]
        if len(candidates) == 1:
            holders[role] = candidates[0]
        else:
            warnings.append({"kind": "unresolved_role_holder", "role": role})
    expected = []
    titles = confirmations.get("title_overrides", {})
    for person in reference:
        name = person.get("full_name")
        occupied = next((role for role, holder in holders.items() if holder is person), None)
        manager_role, evidence = None, "Individual reporting assignment requires HR confirmation"
        if occupied == "Managing Director":
            manager_role, evidence = "Board of Directors", "Chart role edge; named Board identity not supplied"
        elif occupied == "Executive Director":
            evidence = "Chart shows lateral MD/Executive connection, not an ordinary manager edge"
        elif occupied:
            manager_role, evidence = "Managing Director", "Named chart-role holder; direct chart reporting edge"
        elif person.get("department") in TEAM_MANAGERS:
            manager_role = TEAM_MANAGERS[person["department"]]
            evidence = "Explicit reference team branch; individual exceptions still require HR review"
        manager = holders.get(manager_role)
        expected.append({"full_name": name, "department": person.get("department"),
                         "role_title": titles.get(name, person.get("role_title")),
                         "work_emails": person.get("work_emails", []),
                         "manager_name": manager.get("full_name") if manager else None,
                         "manager_role": manager_role, "evidence": evidence,
                         "manager_resolved": manager is not None})
    return expected, holders.get("Operations Coordinator"), warnings


def verify_reporting(employees, solvers, reference, solver_reference, confirmations, tenant="solvit"):
    def scoped(records):
        return [r for r in records if r.get("tenant_id") == tenant or ("tenant_id" not in r and tenant == "solvit")]
    employees, solvers = scoped(employees), scoped(solvers)
    expected, solver_manager, warnings = expected_reporting(reference, confirmations)
    aliases = defaultdict(set)
    for index, record in enumerate(employees):
        for raw in (record.get("id"), record.get("_id")):
            key = reference_key(raw)
            if key: aliases[key].add(index)

    def resolve(raw):
        matches = aliases.get(reference_key(raw), set())
        if len(matches) != 1: return None, "invalid" if not matches else "ambiguous"
        index = next(iter(matches))
        record = employees[index]
        canonical = reference_key(record.get("id") or record.get("_id"))
        if aliases.get(canonical) != {index}: return None, "ambiguous"
        return index, "resolved"

    parents = {}
    for index, record in enumerate(employees):
        parent, state = resolve(record.get("line_manager_id"))
        if state == "resolved": parents[index] = parent
    cycles, done = set(), set()
    for start in parents:
        path, positions, current = [], {}, start
        while current in parents and current not in done and current not in positions:
            positions[current] = len(path); path.append(current); current = parents[current]
        if current in positions: cycles.update(path[positions[current]:])
        done.update(path)

    rows, matched_employees, matched_solvers = [], set(), set()

    def compare(person, records, segment, used):
        matches = {i for i, r in enumerate(records) if clean(r.get("full_name")) == clean(person.get("full_name"))}
        if segment == "FTE":
            expected_emails = set(map(clean, person.get("work_emails", []))) - {""}
            matches.update(i for i, r in enumerate(records) if clean(r.get("work_email")) in expected_emails)
        used.update(matches)
        row = {"segment": segment, "reference_name": person.get("full_name"),
               "reference_department": person.get("department"), "expected_manager_name": person.get("manager_name"),
               "expected_manager_role": person.get("manager_role"), "evidence": person.get("evidence"),
               "current_manager": None, "issues": [], "verification_status": "unverified"}
        if not matches:
            row["issues"].append("missing_reference_record"); rows.append(row); return
        if len(matches) != 1:
            row["issues"].append("ambiguous_record_match"); rows.append(row); return
        index = next(iter(matches)); record = records[index]
        row["snapshot_label"] = ("E" if segment == "FTE" else "S") + f"{index + 1:06d}"
        row["current_department"] = text(record.get("department"))
        row["current_role"] = text(record.get("role_title"))
        row["current_status"] = next((text(record.get(f)) for f in ("lifecycle_state", "employment_status", "status") if text(record.get(f))), None)
        if any(token(record.get(field)) in ("exited", "deactivated", "terminated") for field in ("lifecycle_state", "employment_status", "status")):
            row["issues"].append("reference_member_is_exited")
        if segment == "FTE":
            if clean(record.get("department")) != clean(person.get("department")): row["issues"].append("department_mismatch")
            if token(record.get("employment_type")) not in ("fte", "fulltime"): row["issues"].append("employment_classification_needs_review")
            if clean(record.get("role_title")) != clean(person.get("role_title")): row["issues"].append("title_mismatch")
            if expected_emails and clean(record.get("work_email")) not in expected_emails: row["issues"].append("work_contact_email_mismatch")
        raw_manager = record.get("line_manager_id")
        if raw_manager in (None, ""):
            if person.get("manager_role") not in (None, "Board of Directors"):
                row["issues"].append("missing_manager_assignment")
        else:
            parent, state = resolve(raw_manager)
            if state != "resolved": row["issues"].append(state + "_manager_reference")
            else:
                manager = employees[parent]
                row["current_manager"] = {key: text(manager.get(key)) for key in ("full_name", "department", "role_title")}
                if any(token(manager.get(field)) in ("exited", "deactivated", "terminated") for field in ("lifecycle_state", "status", "employment_status")):
                    row["issues"].append("manager_is_exited")
                target_matches = {i for i, r in enumerate(employees) if clean(r.get("full_name")) == clean(person.get("manager_name"))}
                if person.get("manager_resolved") and len(target_matches) == 1:
                    target = next(iter(target_matches))
                    canonical = employees[target].get("id") or employees[target].get("_id")
                    chosen, resolution = resolve(canonical)
                    if resolution != "resolved" or chosen != target: row["issues"].append("expected_manager_identity_ambiguous")
                    elif parent != target:
                        row["issues"].append("manager_differs_from_reference")
                        row["proposed_manager_record_label"] = f"E{target + 1:06d}"
                elif person.get("manager_resolved"): row["issues"].append("expected_manager_missing_or_ambiguous")
        if segment == "FTE" and index in cycles: row["issues"].append("reporting_cycle")
        if not person.get("manager_resolved"): row["issues"].append("reference_manager_requires_hr_confirmation")
        row["verification_status"] = "review_required" if row["issues"] else "matches_reference_proposal"
        rows.append(row)

    for person in expected: compare(person, employees, "FTE", matched_employees)
    for person in solver_reference:
        target = {"full_name": person.get("full_name"), "manager_name": (solver_manager or {}).get("full_name"),
                  "manager_role": "Operations Coordinator / Head of Solvers", "manager_resolved": solver_manager is not None,
                  "evidence": "Chart Solver branch plus named reference role holder; individual exceptions require HR review"}
        compare(target, solvers, "Solver", matched_solvers)
    return {"read_only": True, "tenant": tenant, "reference_counts": {"fte": len(reference), "solvers": len(solver_reference)},
            "snapshot_counts": {"employees": len(employees), "solvers": len(solvers)}, "rows": rows,
            "extra_employee_labels": [f"E{i+1:06d}" for i in range(len(employees)) if i not in matched_employees],
            "extra_solver_labels": [f"S{i+1:06d}" for i in range(len(solvers)) if i not in matched_solvers],
            "reference_warnings": warnings,
            "notice": "Reference alignment is not HR approval or permission to change records. No writes were performed."}
