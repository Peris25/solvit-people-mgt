"""FORM-02 configuration/attempt adapter; existing authentication and write lock."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from database import get_db
from utils.auth import get_current_user
from utils.employee_integrity import integrity_write
from utils import solver_assessments as service

router=APIRouter(prefix='/solver-assessments',tags=['solver-assessments'])
PRIVATE={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}


@router.get('/capabilities')
async def capabilities(request:Request):
    user=await get_current_user(request)
    return JSONResponse(await service.capabilities(get_db(),user),headers=PRIVATE)


@router.get('/administration-options')
async def administration_options(request:Request):
    user=await get_current_user(request)
    return JSONResponse(await service.administration_options(get_db(),user),headers=PRIVATE)


@router.get('/configurations')
async def configurations(request:Request):
    user=await get_current_user(request)
    return JSONResponse(await service.configurations(get_db(),user),headers=PRIVATE)


@router.post('/configurations')
async def create_configuration(request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.save_configuration(db,user,body)
    return JSONResponse(result,headers=PRIVATE)


@router.post('/configurations/{reference}/versions')
async def new_version(reference:str,request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.save_configuration(db,user,body,reference)
    return JSONResponse(result,headers=PRIVATE)


@router.post('/configurations/{reference}/publish')
async def publish(reference:str,request:Request):
    user=await get_current_user(request);db=get_db()
    async with integrity_write(db): result=await service.publish(db,user,reference)
    return JSONResponse(result,headers=PRIVATE)


@router.get('/attempts')
async def attempts(request:Request):
    user=await get_current_user(request)
    return JSONResponse(await service.listing(get_db(),user),headers=PRIVATE)


@router.post('/attempts')
async def assign(request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.assign(db,user,body)
    return JSONResponse(result,headers=PRIVATE)


@router.get('/attempts/{reference}')
async def attempt(reference:str,request:Request):
    user=await get_current_user(request);db=get_db();row,_=await service.load(db,user,reference)
    await service.audit_solver(db,user,'solver.assessment.viewed',fields=['attempt'],entity_type='solver_assessment',entity_id=row['id'])
    return JSONResponse(service.projection(row,user),headers=PRIVATE)


@router.post('/attempts/{reference}/parts/{part}/{action}')
async def progress(reference:str,part:str,action:str,request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.progress(db,user,reference,part,action,body)
    return JSONResponse(result,headers=PRIVATE)


@router.post('/attempts/{reference}/{action}')
async def decision(reference:str,action:str,request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.decision(db,user,reference,action,body)
    return JSONResponse(result,headers=PRIVATE)


@router.get('/solvers/{reference}/competencies')
async def competencies(reference:str,request:Request):
    user=await get_current_user(request)
    return JSONResponse(await service.competencies(get_db(),user,reference),headers=PRIVATE)


@router.post('/solvers/{reference}/competencies')
async def record_competency(reference:str,request:Request):
    user=await get_current_user(request);db=get_db();body=await request.json()
    async with integrity_write(db): result=await service.record_competency(db,user,reference,body)
    return JSONResponse(result,headers=PRIVATE)


@router.get('/attempts/{reference}/documents/{document_id}/download')
async def download_evidence(reference:str,document_id:str,request:Request):
    user=await get_current_user(request)
    return await service.download_evidence(get_db(),user,reference,document_id)
