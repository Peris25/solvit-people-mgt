"""Private, durable policy attachments in MongoDB GridFS, not the deploy filesystem."""
import hashlib
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from gridfs.errors import NoFile
from utils.employee_integrity import tenant_of
from utils.document_uploads import MAX_BYTES


def bucket(db):
    return AsyncIOMotorGridFSBucket(db,bucket_name='policy_attachments')


async def store(db,policy,name,content):
    digest=hashlib.sha256(content).hexdigest()
    reference=await bucket(db).upload_from_stream(name,content,metadata={
        'tenant_id':tenant_of(policy),'policy_storage_id':str(policy['_id']),'sha256':digest})
    return {'file_storage_id':str(reference),'file_sha256':digest,'file_size':len(content)}


async def load(db,policy):
    reference=policy.get('file_storage_id')
    if not isinstance(reference,str) or not ObjectId.is_valid(reference):
        raise HTTPException(404,'No stored policy attachment is available')
    stream=None
    try:
        stream=await bucket(db).open_download_stream(ObjectId(reference))
        metadata=stream.metadata or {}
        if metadata.get('tenant_id')!=tenant_of(policy) or metadata.get('policy_storage_id')!=str(policy['_id']):
            raise HTTPException(404,'No stored policy attachment is available')
        if not 0<stream.length<=MAX_BYTES:
            raise HTTPException(409,'Policy attachment needs administrator review')
        content=await stream.read()
        digest=hashlib.sha256(content).hexdigest()
        if len(content)!=stream.length or digest!=metadata.get('sha256') or digest!=policy.get('file_sha256'):
            raise HTTPException(409,'Policy attachment could not be verified')
        return content
    except NoFile:
        raise HTTPException(404,'Policy attachment is unavailable; HR must restore it')
    finally:
        if stream is not None:stream.close()
