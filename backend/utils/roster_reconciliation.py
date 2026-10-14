"""Pure offline roster comparison. Report-local labels deliberately omit PII."""
from collections import defaultdict
import re


def clean(value):
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def reference_key(value):
    if isinstance(value, dict):
        if set(value) != {"$oid"} or not isinstance(value["$oid"], str) or not re.fullmatch(r"[a-fA-F0-9]{24}", value["$oid"]):
            return None
        return value["$oid"].lower()
    if value is None:
        return None
    value = str(value)
    return value.lower() if re.fullmatch(r"[a-fA-F0-9]{24}", value) else value or None


def reconcile_roster(records, reference, departments, demo_names=(), exited_names=(), tenant="solvit"):
    records = [r for r in records if r.get("tenant_id", "solvit") == tenant]
    issues = []
    ids, emails, names, aliases = (defaultdict(set) for _ in range(4))
    demo_names, exited_names = set(map(clean, demo_names)), set(map(clean, exited_names))
    approved_departments = set(map(clean, departments))
    matched = set()

    def label(i):
        return f"E{i + 1:06d}"

    def issue(kind, indexes=(), reference_index=None):
        item = {"kind": kind, "records": sorted(label(i) for i in indexes)}
        if reference_index is not None:
            item["reference"] = f"R{reference_index + 1:06d}"
        issues.append(item)

    for i, record in enumerate(records):
        key = reference_key(record.get("id"))
        if key:
            ids[key].add(i)
        for value in (record.get("id"), record.get("_id")):
            key = reference_key(value)
            if key:
                aliases[key].add(i)
        for value in (record.get("work_email"),):
            if clean(value): emails[clean(value)].add(i)
        if clean(record.get("full_name")): names[clean(record["full_name"])].add(i)
        states = {re.sub(r"[^a-z]", "", clean(record.get(field)))
                  for field in ("lifecycle_state", "employment_status", "status") if clean(record.get(field))}
        if "exited" in states:
            issue("exited_record", [i])
        if len(states) > 1:
            issue("conflicting_status_fields", [i])
        if clean(record.get("full_name")) in exited_names and "exited" not in states:
            issue("reference_exit_requires_review", [i])
        if clean(record.get("full_name")) in demo_names or record.get("is_demo") is True:
            issue("demo_candidate_requires_review", [i])
        if clean(record.get("department")) not in approved_departments:
            issue("department_not_in_reference_structure", [i])

    for kind, index in (("duplicate_identifier", ids), ("duplicate_work_email", emails), ("potential_duplicate_name", names),
                        ("ambiguous_identity_alias", aliases)):
        for group in index.values():
            if len(group) > 1: issue(kind, group)

    for j, expected in enumerate(reference):
        contact_emails = expected.get("work_emails", [expected.get("work_email")])
        matches = set(names.get(clean(expected.get("full_name")), ()))
        for email in contact_emails:
            matches.update(emails.get(clean(email), ()))
        if not matches:
            issue("missing_reference_record", reference_index=j)
            continue
        matched.update(matches)
        if len(matches) > 1:
            issue("ambiguous_roster_match", matches, j)
            continue
        i = next(iter(matches))
        record = records[i]
        if clean(record.get("full_name")) != clean(expected.get("full_name")):
            issue("name_mismatch", [i], j)
        if clean(record.get("department")) != clean(expected.get("department")):
            issue("department_mismatch", [i], j)
        if clean(record.get("work_email")) not in set(map(clean, contact_emails)):
            issue("work_contact_email_mismatch", [i], j)
        if clean(record.get("role_title")) != clean(expected.get("role_title")):
            issue("title_mismatch", [i], j)

    for i, record in enumerate(records):
        if i not in matched:
            issue("extra_record_requires_review", [i])
        manager = record.get("line_manager_id")
        if manager not in (None, "") and len(aliases.get(reference_key(manager), ())) != 1:
            issue("unresolved_manager", [i])

    return {"read_only": True, "reference_count": len(reference), "snapshot_count": len(records),
            "issues": issues, "notes": [
                "Labels refer to tenant-filtered input order within this report, not database identifiers.",
                "Potential matches and demo flags require HR confirmation; no changes are proposed automatically.",
                "Team contact emails can be shared inboxes; a mismatch does not authorize changing a login email."]}
