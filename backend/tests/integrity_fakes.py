"""Small asynchronous repository fake for isolated integrity regression tests."""
import asyncio
import re
from copy import deepcopy
from types import SimpleNamespace

from bson import ObjectId
from pymongo.errors import DuplicateKeyError


def expression(value, doc):
    if isinstance(value, str) and value.startswith("$"):
        return doc.get(value[1:])
    if not isinstance(value, dict):
        return value
    if "$eq" in value:
        left, right = value["$eq"]
        return expression(left, doc) == expression(right, doc)
    if "$convert" in value:
        return str(expression(value["$convert"]["input"], doc) or "")
    if "$trim" in value:
        return expression(value["$trim"]["input"], doc).strip()
    if "$toLower" in value:
        return expression(value["$toLower"], doc).lower()
    raise AssertionError("Unsupported test expression")


def field_value(doc, path):
    value = doc
    for part in path.split('.'):
        if not isinstance(value, dict): return None
        value = value.get(part)
    return value


def matches(doc, query):
    for key, expected in query.items():
        if key == "$and":
            if not all(matches(doc, q) for q in expected):
                return False
        elif key == "$or":
            if not any(matches(doc, q) for q in expected):
                return False
        elif key == "$expr":
            if not expression(expected, doc):
                return False
        elif isinstance(expected, dict):
            actual = field_value(doc, key)
            for operator, value in expected.items():
                if operator == "$ne" and actual == value:
                    return False
                if operator == "$nin" and actual in value:
                    return False
                if operator == "$in" and actual not in value:
                    return False
                if operator == "$exists" and (key in doc) != value:
                    return False
                if operator == "$regex" and not re.search(value, str(actual or ""), re.I if expected.get("$options") == "i" else 0):
                    return False
        elif field_value(doc, key) != expected:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    async def to_list(self, length):
        await asyncio.sleep(0)
        return self.docs if length is None else self.docs[:length]

    def sort(self, *args):
        return self

    def limit(self, number):
        self.docs = self.docs[:number]
        return self

    def __aiter__(self):
        async def items():
            for doc in self.docs:
                yield doc
        return items()


class Collection:
    def __init__(self, docs=()):
        self.docs = deepcopy(list(docs))
        self.writes = 0

    def find(self, query=None, projection=None):
        return Cursor([d for d in self.docs if matches(d, query or {})])

    async def find_one(self, query, projection=None):
        rows = await self.find(query).to_list(1)
        return rows[0] if rows else None

    async def insert_many(self, docs):
        return [await self.insert_one(doc) for doc in docs]

    async def insert_one(self, doc):
        doc = deepcopy(doc)
        doc.setdefault("_id", ObjectId())
        if any(d["_id"] == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("Duplicate test key")
        self.docs.append(doc)
        self.writes += 1
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update, upsert=False):
        if upsert and not await self.find_one(query):
            await self.insert_one(query)
        for doc in self.docs:
            if matches(doc, query):
                doc.update(deepcopy(update.get("$set", {})))
                self.writes += 1
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def find_one_and_update(self, query, update, return_document=True, upsert=False):
        if upsert and not await self.find_one(query):
            await self.insert_one(query)
        await self.update_one(query, update)
        return await self.find_one(query)

    async def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if matches(doc, query):
                self.docs.pop(i)
                self.writes += 1
                break


class Database:
    def __init__(self, employees=(), users=(), candidates=()):
        self.employees = Collection(employees)
        self.users = Collection(users)
        self.candidates = Collection(candidates)
        self.integrity_locks = Collection()
        self.audit_logs = Collection()
        self.audit_log = Collection()
        self.revoked_refresh_tokens = Collection()
        self.user_session_invalidations = Collection()
        self.system_settings = Collection()


def employee(key="staff", email="staff@example.com", **kwargs):
    return {"_id": ObjectId(), "id": key, "tenant_id": "solvit", "work_email": email,
            "full_name": key, "lifecycle_state": "Active", **kwargs}


def account(email="staff@example.com", **kwargs):
    return {"_id": ObjectId(), "tenant_id": "solvit", "email": email, "role": "employee", **kwargs}
