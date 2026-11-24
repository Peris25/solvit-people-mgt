import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from bson import ObjectId
from fastapi import HTTPException
import pytest
from utils import policy_storage
from routes import policies
from .test_legacy_security import sut,add

class Bucket:
    def __init__(self):self.files={}
    async def upload_from_stream(self,name,content,metadata):
        key=ObjectId();self.files[key]=(content,metadata);return key
    async def open_download_stream(self,key):
        content,metadata=self.files[key]
        return SimpleNamespace(metadata=metadata,length=len(content),read=AsyncMock(return_value=content),close=Mock())

def test_storage_checks_tenant_policy_and_digest():
    store=Bucket();row={'_id':ObjectId(),'tenant_id':'solvit'}
    with patch.object(policy_storage,'bucket',return_value=store):
        row.update(asyncio.run(policy_storage.store(None,row,'policy.pdf',b'private source')))
        assert asyncio.run(policy_storage.load(None,row))==b'private source'
        for change in ({'tenant_id':'other'},{'_id':ObjectId()},{'file_sha256':'wrong'}):
            with pytest.raises(HTTPException):asyncio.run(policy_storage.load(None,{**row,**change}))

def test_policy_upload_is_readable_without_local_files_and_requires_audience_access(sut,tmp_path):
    db,_,as_role,_=sut;store=Bucket()
    record=add(db.policies,id='durable',status='Draft',applies_to=['employees'],version='2',title='Synthetic policy')
    content=b'%PDF-1.4\nSynthetic policy\n%%EOF'
    with patch.object(policy_storage,'bucket',return_value=store),patch('utils.document_uploads.scan_content',AsyncMock()),patch.object(policies,'UPLOAD_ROOT',tmp_path),patch.object(policies,'notify_publication',AsyncMock()):
        result=as_role('hr_admin').post('/api/policies/durable/upload',files={'file':('policy.pdf',content,'application/pdf')})
        assert result.status_code==200,result.text
        assert not list(tmp_path.iterdir()) and record['file_storage_id']
        assert as_role('employee').get('/api/policies/durable/download').status_code==403
        assert as_role('hr_admin').put('/api/policies/durable',json={'status':'Active'}).status_code==200
        result=as_role('employee').get('/api/policies/durable/download')
        assert result.status_code==200 and result.content==content
        assert result.headers['cache-control']=='private, no-store'
        assert as_role('employee').post('/api/policies/durable/acknowledge',json={'signature':'Synthetic employee'}).status_code==200
        record['applies_to']=['finance']
        assert as_role('employee').get('/api/policies/durable/download').status_code==403

def test_legacy_published_documents_keep_explicit_audience_and_acknowledgement(sut):
    db,_,as_role,_=sut
    add(db.policies,id='published',status='Published',applies_to=['employees'],version='2',content='Approved synthetic content')
    add(db.policies,id='restricted',status='Published',applies_to=['finance'],content='Restricted synthetic content')
    add(db.policies,id='placeholder',status='Published')
    rows=as_role('employee').get('/api/policies').json()
    assert len(rows)==1 and rows[0]['status']=='Active' and rows[0]['content']=='Approved synthetic content'
    assert as_role('employee').post('/api/policies/published/acknowledge',json={'signature':'Synthetic employee'}).status_code==200
