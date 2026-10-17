from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, Response
from database import get_db
from utils.auth import get_current_user
from utils import administrative_reporting as service
router=APIRouter(prefix='/reporting',tags=['reporting'])
PRIVATE={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}

@router.get('/catalogue')
async def catalogue(request:Request):
    user=await get_current_user(request)
    return JSONResponse(service.catalogue(user),headers=PRIVATE)

@router.get('/audit')
async def audit(request:Request,date_from:str|None=None,date_to:str|None=None,event_type:str|None=None,module:str|None=None,actor:str|None=None,offset:int=Query(0,ge=0,le=10000),limit:int=Query(100,ge=1,le=500)):
    user=await get_current_user(request);db=get_db()
    result=await service.audit_feed(db,user,date_from=date_from,date_to=date_to,event_type=event_type,module=module,actor=actor,offset=offset,limit=limit)
    await service.access_audit(db,user,'report.audit.viewed',count=len(result['items']))
    return JSONResponse(result,headers=PRIVATE)

@router.get('/reports/{kind}')
async def report(kind:str,request:Request,date_from:str|None=None,date_to:str|None=None,department:str|None=None,status:str|None=None,offset:int=Query(0,ge=0,le=10000),limit:int=Query(100,ge=1,le=500)):
    user=await get_current_user(request);db=get_db()
    result=await service.report_data(db,user,kind,date_from=date_from,date_to=date_to,department=department,status=status,offset=offset,limit=limit)
    await service.access_audit(db,user,'report.viewed',report=kind,count=len(result['items']))
    return JSONResponse(result,headers=PRIVATE)

@router.get('/reports/{kind}/export.{format}')
async def export(kind:str,format:str,request:Request,date_from:str|None=None,date_to:str|None=None,department:str|None=None,status:str|None=None):
    if format not in ('csv','xlsx'):service.fail('Unsupported report export format',404)
    user=await get_current_user(request);db=get_db()
    result=await service.report_data(db,user,kind,date_from=date_from,date_to=date_to,department=department,status=status,export=True)
    content=service.csv_bytes(result['items']) if format=='csv' else service.xlsx_bytes(result['items'])
    await service.access_audit(db,user,'report.exported',report=kind,format=format,count=len(result['items']))
    mime='text/csv' if format=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(content,media_type=mime,headers={**PRIVATE,'Content-Disposition':f'attachment; filename="{kind}.{format}"'})
