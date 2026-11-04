"""Benefit membership only: no payroll calculations, payments or insurer integration."""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from database import get_db
from utils.auth import get_current_user
from utils.employee_integrity import integrity_write, tenant_of, tenant_query, find_employee
from utils import benefits as service
router=APIRouter(prefix='/benefits',tags=['benefits'])

@router.get('/payroll-files')
async def list_payroll_files(request: Request):
    from utils import payroll_documents
    return JSONResponse(await payroll_documents.listing(get_db(), await get_current_user(request)), headers={'Cache-Control': 'no-store'})

@router.post('/payroll-files')
async def upload_payroll_file(request: Request, file: UploadFile = File(...)):
    from utils import payroll_documents
    from routes.documents import UPLOAD_ROOT
    return await payroll_documents.upload(get_db(), await get_current_user(request), file, UPLOAD_ROOT)

@router.get('/payroll-files/{reference}/download')
async def download_payroll_file(reference: str, request: Request):
    from utils import payroll_documents
    from utils.document_uploads import MIME
    from routes.documents import UPLOAD_ROOT
    path, name = await payroll_documents.download(get_db(), await get_current_user(request), reference, UPLOAD_ROOT)
    return FileResponse(path, filename=name, media_type=MIME['.xlsx'], headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

async def body(request):
    value=await request.json()
    if not isinstance(value,dict): raise HTTPException(422,'An object body is required')
    return value

@router.get('/me')
async def my_benefits(request:Request):
    return await service.overview(get_db(),await get_current_user(request))

@router.get('/schemes')
async def list_schemes(request:Request):
    user=await get_current_user(request)
    service.privileged(user,finance=user.get('role')=='finance')
    rows=await get_db().benefit_schemes.find(tenant_query(tenant_of(user))).to_list(None)
    return [service.scheme_view(row) for row in rows]

@router.post('/schemes')
async def create_scheme(request:Request):
    user=await get_current_user(request); data=await body(request); db=get_db()
    async with integrity_write(db): return await service.save_scheme(db,user,data)

@router.put('/schemes/{scheme_id}')
async def update_scheme(scheme_id:str,request:Request):
    user=await get_current_user(request); data=await body(request); db=get_db()
    async with integrity_write(db): return await service.save_scheme(db,user,data,scheme_id)

@router.post('/requests')
async def request_membership(request:Request):
    user=await get_current_user(request); data=await body(request); db=get_db()
    async with integrity_write(db): return await service.submit(db,user,data)

@router.get('/requests')
async def list_memberships(request:Request):
    user=await get_current_user(request); service.privileged(user,finance=user.get('role')=='finance'); db=get_db()
    rows=await db.benefit_requests.find(tenant_query(tenant_of(user))).sort('created_at',-1).to_list(None)
    result=[]
    for row in rows:
        employee=await find_employee(db,row.get('employee_id'),tenant_of(user))
        if employee and not service.restricted(employee.get('board_only')): result.append(service.request_view(row,employee,user))
    return result

@router.put('/requests/{request_id}/decision')
async def decide_membership(request_id:str,request:Request):
    user=await get_current_user(request); data=await body(request); db=get_db()
    async with integrity_write(db): return await service.decide(db,user,request_id,data)

@router.get('/premiums')
async def list_premiums(request:Request):
    user=await get_current_user(request); service.privileged(user,finance=True)
    rows=await get_db().benefit_premiums.find(tenant_query(tenant_of(user))).to_list(None)
    return [{key:row.get(key) for key in ('scheme_id','month','amount_kes','approval_reference','recorded_at')} for row in rows]

@router.put('/schemes/{scheme_id}/premium')
async def record_premium(scheme_id:str,request:Request):
    user=await get_current_user(request); data=await body(request); db=get_db()
    async with integrity_write(db): return await service.premium(db,user,scheme_id,data)
