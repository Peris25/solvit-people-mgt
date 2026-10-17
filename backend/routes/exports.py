"""Compatibility CSV routes sharing the same safe reporting projections."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from database import get_db
from utils.auth import get_current_user
from utils.employee_integrity import tenant_of, tenant_query
from utils.access_matrix import get_module_access
from utils import administrative_reporting as reporting
router=APIRouter(prefix='/exports',tags=['exports'])

def _csv_response(rows,filename):
    return Response(reporting.csv_bytes(rows),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.get('/employees.csv')
async def export_employees(request:Request):
    user=await get_current_user(request);db=get_db()
    result=await reporting.report_data(db,user,'employees',export=True)
    await reporting.access_audit(db,user,'report.exported',report='employees',format='csv',count=len(result['items']))
    return _csv_response(result['items'],'employees.csv')

async def financial_export(request,kind,module,fields):
    user=await get_current_user(request);entry=get_module_access(module,user.get('role'))
    if user.get('role') not in {'hr_admin','hr_manager','finance'} or not entry or entry.get('level') not in {'Read','Manage','Full'} or entry.get('scope') not in (None,'no_perf_no_disciplinary'):raise HTTPException(403,'Financial report permission is required')
    db=get_db();rows=await getattr(db,kind).find(tenant_query(tenant_of(user))).to_list(10001)
    if len(rows)>10000:raise HTTPException(413,'Financial export exceeds 10000 rows')
    result=[]
    for row in rows:
        safe={key:reporting.scalar(row.get(key)) for key in fields}
        if 'roles' in fields: safe['roles']=', '.join(v for v in row.get('roles',[]) if isinstance(v,str)) if isinstance(row.get('roles'),list) else ''
        result.append(safe)
    await reporting.access_audit(db,user,'report.exported',report=kind,format='csv',count=len(result))
    return _csv_response(result,kind+'.csv')

@router.get('/pay-bands.csv')
async def export_pay_bands(request:Request):
    return await financial_export(request,'pay_bands','M10',('band','min_kes','mid_kes','max_kes','roles'))

@router.get('/budget-allocations.csv')
async def export_budget_allocations(request:Request):
    return await financial_export(request,'budget_allocations','M12',('initiative_name','budget_cycle','linked_module','amount_kes','spent_amount_kes','variance_kes','status','created_at','approved_at','spent_at'))
