"""
Audit script — verifies every email template renders a non-empty body when its
action fires. Walks every function in routes/, automation/, utils/ via AST, and:

  • Recognises calls: fire_and_forget(db, "key", ..., extra={...})
                      trigger(db, "key", ..., extra={...})
                      send_email(db, ..., template_key="key", context={...})
  • Resolves `extra=variable` / `context=variable` to the dict literal
    assigned to that variable in the same function scope.
  • Resolves dynamic template_key via simple `mapping = {literal: literal}`
    dicts whose values look like template keys (e.g. "disciplinary.hearing").
  • For each (template_key, supplied_extras) pair, compares against the
    {{placeholders}} found in the template body+subject pulled from MongoDB.

Exits 0 if every wired template renders fully, 1 otherwise.
"""
import asyncio
import ast
import os
import re
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

THIS_DIR = Path(__file__).resolve().parent
load_dotenv(THIS_DIR.parent / ".env")

ROOTS = [THIS_DIR.parent / d for d in ("routes", "automation", "utils")]

STANDARD_TAGS = {
    "employee_name", "employee_first_name", "employee_email", "employee_role",
    "employee_department", "role_title", "department", "start_date",
    "line_manager_name", "line_manager_email", "manager_name", "manager_email",
    "hr_name", "company_name", "platform_link", "login_url", "action_date",
    "due_date", "current_year", "today",
}

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]+$")


def dict_keys(node: ast.AST) -> set[str]:
    """Return string keys of an ast.Dict literal."""
    if not isinstance(node, ast.Dict):
        return set()
    out = set()
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            out.add(k.value)
        elif k is None and isinstance(v, ast.Name):
            # {**variable, ...} — we'd need to chase the variable
            pass
    return out


def collect_local_dicts(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.Dict]:
    """Map variable name -> Dict node assigned to it in this function."""
    locals_ = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Dict):
            locals_[node.targets[0].id] = node.value
    return locals_


def collect_local_mappings(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, set[str]]:
    """Map variable name -> set of dict VALUES (string) assigned to it,
    used to enumerate template keys for dynamic template_key=mapping[x]."""
    out = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Dict):
            vals = set()
            for v in node.value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str) \
                        and TEMPLATE_KEY_RE.match(v.value):
                    vals.add(v.value)
            if vals:
                out[node.targets[0].id] = vals
    return out


def resolve_extras(extra_node: ast.AST | None, local_dicts: dict[str, ast.Dict]) -> set[str]:
    if extra_node is None:
        return set()
    if isinstance(extra_node, ast.Dict):
        keys = dict_keys(extra_node)
        # Also follow {**variable, ...} spreads
        for k, v in zip(extra_node.keys, extra_node.values):
            if k is None and isinstance(v, ast.Name) and v.id in local_dicts:
                keys |= dict_keys(local_dicts[v.id])
        return keys
    if isinstance(extra_node, ast.Name) and extra_node.id in local_dicts:
        return dict_keys(local_dicts[extra_node.id])
    return set()


def collect_local_template_key_aliases(func, local_mappings: dict[str, set[str]]) -> dict[str, set[str]]:
    """Trace `name = mapping.get(x, "default")` or `name = mapping[x]` or
    `name = "literal.template_key"` assignments inside the function. Returns
    {variable_name: set(possible_template_key_strings)}.
    """
    out: dict[str, set[str]] = {}
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 \
                or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0].id
        rhs = node.value
        keys: set[str] = set()
        if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str) \
                and TEMPLATE_KEY_RE.match(rhs.value):
            keys.add(rhs.value)
        elif isinstance(rhs, ast.Call) and isinstance(rhs.func, ast.Attribute) \
                and rhs.func.attr == "get" and isinstance(rhs.func.value, ast.Name):
            keys |= local_mappings.get(rhs.func.value.id, set())
            # also include the default arg if literal
            if len(rhs.args) >= 2 and isinstance(rhs.args[1], ast.Constant) \
                    and isinstance(rhs.args[1].value, str) \
                    and TEMPLATE_KEY_RE.match(rhs.args[1].value):
                keys.add(rhs.args[1].value)
        elif isinstance(rhs, ast.Subscript) and isinstance(rhs.value, ast.Name):
            keys |= local_mappings.get(rhs.value.id, set())
        elif isinstance(rhs, ast.IfExp):
            for branch in (rhs.body, rhs.orelse):
                if isinstance(branch, ast.Constant) and isinstance(branch.value, str) \
                        and TEMPLATE_KEY_RE.match(branch.value):
                    keys.add(branch.value)
        if keys:
            out[target] = keys
    return out


def resolve_template_keys(key_node: ast.AST, local_mappings: dict[str, set[str]],
                          local_aliases: dict[str, set[str]]) -> set[str]:
    """Return one or more possible template keys for a call's template_key arg."""
    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
        return {key_node.value}
    if isinstance(key_node, ast.Call) and isinstance(key_node.func, ast.Attribute) \
            and key_node.func.attr == "get" and isinstance(key_node.func.value, ast.Name):
        out = set(local_mappings.get(key_node.func.value.id, set()))
        if len(key_node.args) >= 2 and isinstance(key_node.args[1], ast.Constant) \
                and isinstance(key_node.args[1].value, str) \
                and TEMPLATE_KEY_RE.match(key_node.args[1].value):
            out.add(key_node.args[1].value)
        return out
    if isinstance(key_node, ast.Subscript) and isinstance(key_node.value, ast.Name):
        return local_mappings.get(key_node.value.id, set())
    if isinstance(key_node, ast.Name):
        return local_aliases.get(key_node.id, set())
    return set()


def scan():
    """Return {template_key: set(extra_keys aggregated across all sites)}."""
    sites: dict[str, set[str]] = {}
    for root in ROOTS:
        for py in root.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(), filename=str(py))
            except SyntaxError:
                continue
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                local_dicts = collect_local_dicts(func)
                local_mappings = collect_local_mappings(func)
                local_aliases = collect_local_template_key_aliases(func, local_mappings)
                for node in ast.walk(func):
                    if not isinstance(node, ast.Call):
                        continue
                    f = node.func
                    fname = (f.attr if isinstance(f, ast.Attribute)
                             else f.id if isinstance(f, ast.Name) else None)
                    if fname not in ("fire_and_forget", "trigger", "send_email"):
                        continue
                    # Figure out template_key location
                    key_node = None
                    extra_node = None
                    if fname in ("fire_and_forget", "trigger"):
                        if len(node.args) >= 2:
                            key_node = node.args[1]
                        for kw in node.keywords:
                            if kw.arg == "template_key":
                                key_node = kw.value
                            elif kw.arg == "extra":
                                extra_node = kw.value
                    else:  # send_email
                        for kw in node.keywords:
                            if kw.arg == "template_key":
                                key_node = kw.value
                            elif kw.arg == "context":
                                extra_node = kw.value
                    if key_node is None:
                        continue
                    keys = resolve_template_keys(key_node, local_mappings, local_aliases)
                    extras = resolve_extras(extra_node, local_dicts)
                    for k in keys:
                        sites.setdefault(k, set()).update(extras)
    return sites


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    templates = await db.email_templates.find({"tenant_id": "solvit"}).to_list(1000)
    sites = scan()

    print(f"Loaded {len(templates)} templates. Scanned {len(sites)} trigger call sites.\n")

    failures = []
    no_caller = []
    ok = 0

    for tpl in sorted(templates, key=lambda t: t.get("key", "")):
        key = tpl["key"]
        text = (tpl.get("body") or "") + " " + (tpl.get("subject") or "")
        placeholders = set(PLACEHOLDER_RE.findall(text))
        if not placeholders:
            ok += 1
            continue
        caller_extras = sites.get(key)
        if caller_extras is None:
            no_caller.append(key)
            continue
        supplied = STANDARD_TAGS | caller_extras
        missing = placeholders - supplied
        if missing:
            failures.append((key, sorted(missing), sorted(caller_extras)))
        else:
            ok += 1

    print(f"PASS: {ok} templates render fully\n")

    if no_caller:
        print(f"NO-CALLER ({len(no_caller)}) — template exists but is never fired by code today:")
        for k in no_caller:
            print(f"  - {k}")
        print()

    if failures:
        print(f"FAIL ({len(failures)}) — placeholders not supplied -> blank in email:")
        for key, missing, extras in failures:
            print(f"  {key}")
            print(f"    missing: {missing}")
            print(f"    caller extras: {extras}")
        sys.exit(1)
    else:
        print("OK - every wired template renders with all placeholders filled.")


if __name__ == "__main__":
    asyncio.run(main())
