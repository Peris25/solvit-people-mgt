import pytest
from unittest.mock import patch
from fastapi import HTTPException
from utils import performance_workflows as flow
from utils.review_deletion import delete_drafts,version,removable
from utils.notification_centre import list_inbox
from .test_performance_workflows import fixture,create,run,assign,self_body


def request(row):return {'reviews':[{'id':str(row.get('id') or row['_id']),'version':version(row)}],'reason':'Created in error; HR confirmed removal','confirmed':True}


def test_hr_removes_draft_notifications_receipts_and_exact_linked_tasks_only():
 db,users=fixture();result=create(db,users);row=db.performance_reviews.docs[0]
 notification=db.notifications.docs[0]
 run(db.notification_receipts.insert_one({'tenant_id':'solvit','notification_id':notification['id'],'user_id':'synthetic'}))
 run(db.tasks.insert_one({'id':'linked','tenant_id':'solvit','performance_review_id':result['id']}))
 run(db.tasks.insert_one({'id':'unrelated','tenant_id':'solvit','employee_id':'staff'}))
 run(db.notifications.insert_one({'id':'foreign','tenant_id':'foreign','data':{'performance_review_id':result['id']}}))
 assert flow.projection(row,users['hr'],db.employees.docs[0])['can_delete']
 deleted=run(delete_drafts(db,users['hr'],request(row)))
 assert deleted['deleted']==[result['id']] and not db.performance_reviews.docs
 assert [n['id'] for n in db.notifications.docs]==['foreign']
 assert not db.notification_receipts.docs and [t['id'] for t in db.tasks.docs]==['unrelated']
 assert run(list_inbox(db,users['staff']))['unread_count']==0
 assert any(a['event']=='performance.draft.deleted' for a in db.audit_logs.docs)
 # The removed period can be created again without preserving a stale blocker.
 assert run(flow.create_review(db,users['hr'],{'employee_id':'staff','cycle_type':'Year_End','cycle_year':2026}))['id']!=result['id']


@pytest.mark.parametrize('actor',['staff','manager','other','finance'])
def test_non_hr_cannot_delete_even_their_own_draft(actor):
 db,users=fixture();create(db,users);row=db.performance_reviews.docs[0]
 assert not flow.projection(row,users[actor],db.employees.docs[0])['can_delete']
 with pytest.raises(HTTPException):run(delete_drafts(db,users[actor],request(row)))
 assert len(db.performance_reviews.docs)==1


@pytest.mark.parametrize('changes',[{'status':'Self_Draft'},{'status':'Self_Submitted'},{'status':'Completed'},
 {'overall_score':0},{'self_assessment':{'summary':'saved work'}},{'manager_assessment':{'summary':'assessed'}},
 {'employee_signature':'signed'},{'form_data_json':{'answer':'preserve'}},{'released_at':'2099-01-01'}])
def test_submitted_scored_or_evidenced_reviews_are_protected(changes):
 db,users=fixture();create(db,users);row=db.performance_reviews.docs[0];row.update(changes)
 assert not removable(row)
 with pytest.raises(HTTPException):run(delete_drafts(db,users['hr'],request(row)))
 assert len(db.performance_reviews.docs)==1


def test_legacy_empty_draft_can_be_removed_but_stale_version_cannot():
 db,users=fixture();create(db,users);row=db.performance_reviews.docs[0];row.pop('workflow_version')
 body=request(row);row['updated_at']='newer'
 with pytest.raises(HTTPException):run(delete_drafts(db,users['hr'],body))
 assert len(db.performance_reviews.docs)==1
 assert run(delete_drafts(db,users['hr'],request(row)))['deleted']


def test_batch_validates_every_record_and_tenant_before_deleting_anything():
 db,users=fixture();create(db,users);row=db.performance_reviews.docs[0]
 run(db.performance_reviews.insert_one({'id':'foreign','employee_id':'staff','tenant_id':'foreign','status':'Draft'}))
 body=request(row);body['reviews'].append({'id':'foreign','version':version(db.performance_reviews.docs[1])})
 with pytest.raises(HTTPException):run(delete_drafts(db,users['hr'],body))
 assert len(db.performance_reviews.docs)==2


def test_audit_outage_or_linked_submission_preserves_draft():
 db,users=fixture();create(db,users);row=db.performance_reviews.docs[0]
 with patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('synthetic audit outage')):
  with pytest.raises(RuntimeError):run(delete_drafts(db,users['hr'],request(row)))
 assert len(db.performance_reviews.docs)==1
 run(db.form_submissions.insert_one({'tenant_id':'solvit','performance_review_id':row['id'],'status':'Submitted'}))
 with pytest.raises(HTTPException):run(delete_drafts(db,users['hr'],request(row)))
 assert len(db.performance_reviews.docs)==1


def test_orphan_notification_is_hidden_even_if_cleanup_was_interrupted():
 db,users=fixture();create(db,users)
 db.performance_reviews.docs.clear()
 assert db.notifications.docs
 assert run(list_inbox(db,users['staff']))['items']==[]


def test_bulk_removal_affects_only_explicitly_selected_employee_reviews():
 db,users=fixture();create(db,users);first=db.performance_reviews.docs[0]
 run(db.performance_reviews.insert_one({'id':'second','employee_id':'other','tenant_id':'solvit','status':'Draft','cycle_type':'Year_End','cycle_year':2026}))
 run(db.performance_reviews.insert_one({'id':'keep','employee_id':'staff','tenant_id':'solvit','status':'Draft','cycle_type':'Mid_Year','cycle_year':2026}))
 second=db.performance_reviews.docs[1];body=request(first);body['reviews'].append({'id':'second','version':version(second)})
 assert run(delete_drafts(db,users['hr'],body))['deleted']==[first['id'],'second']
 assert [r['id'] for r in db.performance_reviews.docs]==['keep']
