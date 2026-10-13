"""Pure, redacted integrity audit and additive migration plan; never writes data."""
from collections import defaultdict

from fastapi import HTTPException
from utils.employee_integrity import normalize_email, employee_key, tenant_of, INELIGIBLE_MANAGER_STATES


# Prepared for a separately approved migration, NOT installed on app startup.
INDEX_PLAN = [
    {"collection": "users", "keys": [("email_normalized", 1)], "unique": True,
     "name": "uq_user_email_normalized", "partialFilterExpression": {"email_normalized": {"$type": "string"}}},
    {"collection": "employees", "keys": [("tenant_id", 1), ("work_email_normalized", 1)], "unique": True,
     "name": "uq_employee_email_normalized", "partialFilterExpression": {"work_email_normalized": {"$type": "string"}}},
    {"collection": "employees", "keys": [("id", 1)], "unique": True,
     "name": "uq_employee_id", "partialFilterExpression": {"id": {"$type": "string"}}},
    {"collection": "users", "keys": [("tenant_id", 1), ("employee_id", 1)], "unique": True,
     "name": "uq_user_employee", "partialFilterExpression": {"employee_id": {"$type": "string"}}},
    {"collection": "employees", "keys": [("tenant_id", 1), ("employee_code", 1)], "unique": True,
     "name": "uq_employee_code", "partialFilterExpression": {"employee_code": {"$type": "string"}}},
]


def audit_records(employees, users):
    """Labels are report-local, not hashes of identities; no PII is returned."""
    issues, proposals = [], []
    aliases, ids, employee_emails, codes = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    user_emails, owners = defaultdict(list), defaultdict(list)
    employee_labels = {i: f"E{i + 1:06d}" for i in range(len(employees))}
    user_labels = {i: f"U{i + 1:06d}" for i in range(len(users))}

    def issue(kind, labels):
        issues.append({"kind": kind, "records": sorted(set(labels))})

    def email_of(record, field, label):
        try:
            email = normalize_email(record.get(field))
        except HTTPException:
            issue("invalid_email", [label])
            return None
        if record.get(field + "_normalized") != email:
            proposals.append({"record": label, "action": "add_or_review_normalized_email"})
        return email

    for i, employee in enumerate(employees):
        label = employee_labels[i]
        tenant = tenant_of(employee)
        key = employee_key(employee)
        ids[key].append(label)
        for alias in {key, str(employee["_id"])}:
            aliases[(tenant, alias)].append(i)
        if not employee.get("id"):
            proposals.append({"record": label, "action": "add_legacy_object_id_as_canonical_id"})
        if not employee.get("tenant_id"):
            proposals.append({"record": label, "action": "review_legacy_tenant"})
        email = email_of(employee, "work_email", label)
        if email:
            employee_emails[(tenant, email)].append(i)
        code = employee.get("employee_code")
        if isinstance(code, str) and code.strip():
            codes[(tenant, code.strip())].append(label)
        elif code is not None:
            issue("invalid_employee_code", [label])

    for group in ids.values():
        if len(group) > 1:
            issue("duplicate_employee_id", group)
    for group in aliases.values():
        if len(group) > 1:
            issue("ambiguous_employee_reference", [employee_labels[i] for i in group])
    for group in employee_emails.values():
        if len(group) > 1:
            issue("duplicate_employee_email", [employee_labels[i] for i in group])
    for group in codes.values():
        if len(group) > 1:
            issue("duplicate_employee_code", group)

    for i, user in enumerate(users):
        label = user_labels[i]
        email = email_of(user, "email", label)
        if email:
            user_emails[email].append(label)
        link = user.get("employee_id")
        if "employee_id" in user and link is not None and (not isinstance(link, str) or not link.strip()):
            issue("invalid_or_blank_employee_link", [label])
        tenant = tenant_of(user)
        explicit = aliases.get((tenant, str(link)), []) if link else []
        if user.get("account_type") in ("system", "solver", "board"):
            if link:
                issue("exception_account_has_employee_link", [label])
            continue
        if link and str(link) in {str(user.get("_id")), str(user.get("id"))} and not explicit:
            issue("legacy_user_id_as_employee_link", [label])
        elif link and not explicit:
            issue("orphaned_account_link", [label])
        matches = explicit or employee_emails.get((tenant, email), [])
        if len(matches) > 1:
            issue("ambiguous_account_employee", [label] + [employee_labels[j] for j in matches])
        elif len(matches) == 1:
            j = matches[0]
            owners[j].append(label)
            if link != employee_key(employees[j]):
                proposals.append({"record": label, "employee": employee_labels[j], "action": "review_canonical_employee_link"})
        else:
            issue("unlinked_account_requires_classification", [label])

    for group in user_emails.values():
        if len(group) > 1:
            issue("duplicate_account_email", group)
    for j, group in owners.items():
        if len(group) > 1:
            issue("multiple_accounts_for_employee", [employee_labels[j]] + group)
    for j in range(len(employees)):
        if not owners.get(j):
            issue("employee_without_account", [employee_labels[j]])

    parents = {}
    for i, employee in enumerate(employees):
        label = employee_labels[i]
        reference = employee.get("line_manager_id")
        if not reference:
            if employee.get("is_board_chair") is not True:
                issue("missing_manager", [label])
            continue
        matches = aliases.get((tenant_of(employee), str(reference)), [])
        if len(matches) != 1:
            issue("invalid_or_ambiguous_manager", [label])
            continue
        parents[i] = matches[0]
        manager = employees[matches[0]]
        if manager.get("lifecycle_state") in INELIGIBLE_MANAGER_STATES:
            issue("ineligible_manager", [label, employee_labels[matches[0]]])
        if reference != employee_key(manager):
            proposals.append({"record": label, "action": "review_legacy_manager_alias"})

    visited, cycles = set(), set()
    for start in parents:
        path, positions = [], {}
        node = start
        while node in parents and node not in visited:
            if node in positions:
                cycle = tuple(sorted(path[positions[node]:]))
                if cycle not in cycles:
                    cycles.add(cycle)
                    issue("reporting_cycle", [employee_labels[j] for j in cycle])
                break
            positions[node] = len(path)
            path.append(node)
            node = parents[node]
        visited.update(path)

    counts = defaultdict(int)
    for item in issues:
        counts[item["kind"]] += 1
    return {
        "read_only": True, "employees_scanned": len(employees), "accounts_scanned": len(users),
        "issue_counts": dict(counts), "issues": issues, "proposed_reviews": proposals,
        "indexes_ready": not issues and not proposals,
        "index_plan": INDEX_PLAN,
        "notice": "Report-local labels contain no identity mapping. Review all proposals; no changes were applied.",
    }
