"""HR removal of unsubmitted reviews and their explicitly linked portal artifacts."""
import hashlib
import json
from fastapi import HTTPException
from utils.employee_integrity import tenant_of, tenant_query


def version(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def removable(row):
    if row.get("status") != "Draft": return False
    fields = ("self_assessment", "manager_assessment", "hr_summary", "released_at", "released_by", "review_meeting",
        "meeting_proposal", "employee_signature", "manager_signature", "hr_signature", "submitted_at", "completed_at", "form_data_json",
        "section_a_score", "section_b_score", "section_c_score", "section_c_nps", "section_c_csat", "overall_score", "rating", "nine_box_placement")
    return not any(row.get(key) not in (None, "", [], {}) for key in fields)


def linked(tenant, refs):
    return {"$and": [tenant_query(tenant), {"$or": [
        {"performance_review_id": {"$in": refs}}, {"data.performance_review_id": {"$in": refs}},
        {"entity_type": "performance_review", "entity_id": {"$in": refs}}]}]}


async def remove_linked(db, tenant, refs):
    notifications = await db.notifications.find(linked(tenant, refs)).to_list(None)
    for notice in notifications:
        keys = [str(notice["_id"])] + ([str(notice["id"])] if notice.get("id") else [])
        receipts = await db.notification_receipts.find({"$and": [tenant_query(tenant), {"notification_id": {"$in": keys}}]}).to_list(None)
        for receipt in receipts: await db.notification_receipts.delete_one({"_id": receipt["_id"]})
        await db.notifications.delete_one({"_id": notice["_id"]})
    tasks = getattr(db, "tasks", None)
    if tasks is not None:
        for task in await tasks.find(linked(tenant, refs)).to_list(None):
            await tasks.delete_one({"_id": task["_id"]})


async def delete_drafts(db, user, body):
    from utils import performance_workflows as flow
    flow.require_hr(user)
    if not isinstance(body, dict) or set(body) != {"reviews", "reason", "confirmed"} or body.get("confirmed") is not True:
        flow.fail("Confirm the selected draft reviews and provide a deletion reason")
    reason = flow.text(body.get("reason"), "deletion reason", 1500)
    if len(reason) < 10: flow.fail("Provide a clear deletion reason of at least 10 characters")
    selected = body.get("reviews")
    if not isinstance(selected,list) or not 1 <= len(selected) <= 100:
        flow.fail("Select between 1 and 100 draft reviews")
    records=[]; seen=set()
    for entry in selected:
        if not isinstance(entry,dict) or set(entry) != {"id","version"} or not isinstance(entry.get("id"),str):
            flow.fail("Each selected review requires its ID and current version")
        row, employee = await flow.record(db,user,entry['id'])
        if row['_id'] in seen: flow.fail("Select each review only once")
        seen.add(row['_id'])
        if entry['version'] != version(row): flow.fail("A selected review changed. Refresh and review the selection again",409)
        if not removable(row): flow.fail("Only unsubmitted, unscored Draft reviews can be deleted",409)
        refs=[str(row['_id']),row['_id']] + ([str(row['id'])] if row.get('id') else [])
        forms=getattr(db,'form_submissions',None)
        if forms is not None and await forms.find_one(linked(tenant_of(user),refs)):
            flow.fail("A linked form submission must be reviewed before deleting this record",409)
        records.append((row,refs))
    # Validate the entire selection and durably audit it before any deletion.
    for row,refs in records:
        await flow.audit(db,user,'performance.draft.deleted',row,employee_id=row['employee_id'],
            cycle_type=row.get('cycle_type'),cycle_year=row.get('cycle_year'),reason=reason)
    for row,refs in records:
        await db.performance_reviews.delete_one({'_id':row['_id']})
        await remove_linked(db,tenant_of(user),refs)
    return {'deleted':[str(row.get('id') or row['_id']) for row,_ in records]}
