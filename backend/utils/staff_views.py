"""Read-only public staff projections and a bounded, unambiguous reporting forest."""
import re
import hashlib
from collections import defaultdict

from bson import ObjectId, BSON
from utils.employee_integrity import tenant_of, tenant_query
from utils.staff_directory import visible_state, business_email, approved_work_phone

PUBLIC_SOURCE_FIELDS = {
    key: 1 for key in ("_id", "id", "tenant_id", "full_name", "preferred_name", "role_title", "department",
                      "work_email", "lifecycle_state", "status", "employment_status", "work_phone", "work_phone_directory_approved",
                      "role_level", "job_level", "employment_type", "line_manager_id", "board_only")
}
MAX_TREE_DEPTH = 32


def text(value):
    # A whitelisted field containing an unexpected nested document must not leak
    # sensitive data masquerading as public metadata.
    return value if isinstance(value, str) else None


def token(value):
    return re.sub(r"[^a-z0-9]", "", (text(value) or "").lower())


def identifier(value):
    return str(value) if isinstance(value, (str, ObjectId)) and str(value) else None


def restricted(value):
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "")
    return bool(value)


def build_staff_views(records, user, department_names=()):
    tenant = tenant_of(user)
    def in_tenant(record):
        return record.get("tenant_id") == tenant or ("tenant_id" not in record and tenant == "solvit")
    aliases = defaultdict(set)
    for index, record in enumerate(records):
        if not in_tenant(record):
            continue
        for reference in (identifier(record.get("id")), identifier(record.get("_id"))):
            if reference:
                aliases[reference].add(index)

    def resolve(reference):
        reference = identifier(reference)
        if not reference:
            return set()
        found = set(aliases.get(reference, ()))
        if ObjectId.is_valid(reference):
            found.update(aliases.get(str(ObjectId(reference)), ()))
        return found

    department_labels = defaultdict(set)
    for name in department_names:
        if text(name):
            department_labels[token(name)].add(name)
    visible = {}
    for index, record in enumerate(records):
        if not in_tenant(record):
            continue
        if not visible_state(record):
            continue
        if restricted(record.get("board_only")) and user.get("role") not in ("board", "it_admin"):
            continue
        canonical = identifier(record.get("id")) or identifier(record.get("_id"))
        identity_ok = resolve(canonical) == {index} and (record.get("id") in (None, "") or identifier(record.get("id")) is not None)
        safe_id = canonical if identity_ok else identifier(record.get("_id"))
        if resolve(safe_id) != {index}:
            safe_id = None
        department = text(record.get("department"))
        labels = department_labels.get(token(department), set())
        visible[index] = {
            "id": safe_id, "node_id": "staff-" + hashlib.sha256(BSON.encode({"_id": record["_id"]})).hexdigest(),
            "full_name": text(record.get("full_name")), "preferred_name": text(record.get("preferred_name")),
            "role_title": text(record.get("role_title")), "department": department,
            "department_label": next(iter(labels)) if len(labels) == 1 else department,
            "work_email": business_email(record.get("work_email")), "work_phone": approved_work_phone(record),
            "identity_status": "resolved" if identity_ok else "ambiguous",
            "line_manager_id": None, "line_manager_name": None, "reporting_status": "none",
        }

    parents = {}
    for index, node in visible.items():
        reference = records[index].get("line_manager_id")
        if reference is None or reference == "":
            continue
        matches = resolve(reference)
        if len(matches) > 1:
            node["reporting_status"] = "ambiguous"
        elif len(matches) == 1 and next(iter(matches)) in visible:
            parent = next(iter(matches))
            if node["identity_status"] != "resolved" or visible[parent]["identity_status"] != "resolved":
                node["reporting_status"] = "ambiguous"
                continue
            parents[index] = parent
            node.update(line_manager_id=visible[parent]["id"], line_manager_name=visible[parent]["full_name"],
                        reporting_status="resolved")
        else:
            # Missing, excluded or invisible managers have the same public
            # response: no hidden names/identifiers or existence disclosure.
            node["reporting_status"] = "unavailable"

    done, cyclic = set(), set()
    for start in visible:
        path, positions = [], {}
        current = start
        while current in parents and current not in done and current not in positions:
            positions[current] = len(path)
            path.append(current)
            current = parents[current]
        if current in positions:
            cyclic.update(path[positions[current]:])
        done.update(path)
    for index in cyclic:
        parents.pop(index, None)
        visible[index]["reporting_status"] = "cycle"

    # Bound JSON and frontend recursion even for a very long valid chain.
    for index in visible:
        current, depth = index, 0
        while current in parents and depth < MAX_TREE_DEPTH:
            current = parents[current]
            depth += 1
        if current in parents:
            parents.pop(index, None)
            visible[index]["reporting_status"] = "depth_limit"

    directory = sorted(visible.values(), key=lambda node: ((node["full_name"] or "").casefold(), node["node_id"]))
    nodes = {index: {**node, "name": node["full_name"], "direct_reports": []} for index, node in visible.items()}
    roots = []
    for index, node in nodes.items():
        if index in parents:
            nodes[parents[index]]["direct_reports"].append(node)
        else:
            roots.append(node)
    sort_key = lambda node: ((node["name"] or "").casefold(), node["node_id"])
    for node in nodes.values():
        node["direct_reports"].sort(key=sort_key)
    roots.sort(key=sort_key)
    return directory, {"roots": roots, "total": len(nodes),
                       "issues": sum(node["identity_status"] != "resolved" or node["reporting_status"] not in ("none", "resolved")
                                     for node in visible.values())}


async def read_staff_views(db, user):
    # Read all identifiers before visibility filtering: a hidden/exited duplicate
    # must not cause a manager reference to be resolved to the wrong employee.
    records = await db.employees.find(tenant_query(tenant_of(user)), PUBLIC_SOURCE_FIELDS).to_list(None)
    settings = await db.system_settings.find_one({"tenant_id": tenant_of(user), "category": "workforce"},
                                                {"values.departments": 1})
    values = (settings or {}).get("values")
    departments = values.get("departments") if isinstance(values, dict) else None
    departments = departments if isinstance(departments, list) else []
    names = [entry.get("name") if isinstance(entry, dict) else entry
             for entry in departments]
    return build_staff_views(records, user, names)
