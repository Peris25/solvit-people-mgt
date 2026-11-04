import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from fastapi import HTTPException,UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request
from routes import solver_intake as route
from .integrity_fakes import Collection

PDF=b'%PDF-1.4\n'+b'synthetic CV only '*10+b'\n%%EOF'
def run(c):return asyncio.run(c)
def upload(content=PDF,name='synthetic-cv.pdf',mime='application/pdf'):
 return UploadFile(BytesIO(content),filename=name,headers=Headers({'content-type':mime}))


def test_clean_pdf_is_validated_and_scanned_with_bounded_read():
 file=upload();file.read=AsyncMock(return_value=PDF)
 with patch('utils.document_uploads.scan_content',new=AsyncMock()) as scan:
  ext,content=run(route._read_clean_cv(file))
 assert ext=='.pdf' and content==PDF
 file.read.assert_awaited_once_with(route.CV_MAX_BYTES+1);scan.assert_awaited_once_with(PDF)


@pytest.mark.parametrize('status',[422,503])
def test_malware_or_unavailable_scanner_rejects_cv(status):
 with patch('utils.document_uploads.scan_content',new=AsyncMock(side_effect=HTTPException(status,'synthetic scanner rejection'))):
  with pytest.raises(HTTPException) as error:run(route._read_clean_cv(upload()))
 assert error.value.status_code==status


@pytest.mark.parametrize('content,name,mime',[(b'not a PDF '*20,'bad.pdf','application/pdf'),(PDF,'bad.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document'),(b'%PDF-'+b'x'*(route.CV_MAX_BYTES),'big.pdf','application/pdf'),(b'%PDF-1.4 no eof'+b'x'*90,'bad.pdf','application/pdf')],ids=['invalid','mismatch','oversize','truncated'])
def test_mismatch_truncated_pdf_and_size_are_rejected_before_scan(content,name,mime):
 with patch('utils.document_uploads.scan_content',new=AsyncMock()) as scan:
  with pytest.raises(HTTPException):run(route._read_clean_cv(upload(content,name,mime)))
 scan.assert_not_awaited()


def fixture():
 db=SimpleNamespace(**{name:Collection() for name in ('solver_requisitions','candidates','ineligible_applicants','audit_logs')})
 run(db.solver_requisitions.insert_one({'id':'req','tenant_id':'solvit','status':'Open','working_areas':['All counties']}))
 return db


def apply(cv):
 return route.public_apply('req',Request({'type':'http','headers':[],'client':('127.0.0.1',1234)}),
  full_name='Synthetic Applicant',phone_number='0700000001',email='applicant@example.com',county='Nairobi City',town_area='Synthetic town',
  has_driving_licence=True,qualifications='["Sound knowledge of vehicles and assets to be inspected"]',previous_inspector_company=None,
  has_smartphone=True,availability='Yes',commission_acknowledged=True,channel='Other',challenge_token='synthetic-test-only',challenge_answer='0',website_url='',cv=cv)


def test_public_cv_scanner_failure_never_writes_file_or_candidate(tmp_path):
 db=fixture()
 with patch.object(route,'get_db',return_value=db),patch.object(route,'CV_UPLOAD_ROOT',tmp_path),patch.object(route,'_rate_limit_check',return_value=False),patch.object(route,'_verify_captcha',return_value=(True,'')),patch('utils.document_uploads.scan_content',new=AsyncMock(side_effect=HTTPException(503,'Scanner unavailable'))):
  with pytest.raises(HTTPException):run(apply(upload()))
 assert not list(tmp_path.iterdir()) and not db.candidates.docs and not db.ineligible_applicants.docs and not db.audit_logs.docs


def test_public_clean_cv_is_private_audited_and_linked_to_applicant(tmp_path):
 db=fixture()
 with patch.object(route,'get_db',return_value=db),patch.object(route,'CV_UPLOAD_ROOT',tmp_path),patch.object(route,'_rate_limit_check',return_value=False),patch.object(route,'_verify_captcha',return_value=(True,'')),patch('utils.document_uploads.scan_content',new=AsyncMock()),patch('utils.email_triggers.fire_and_forget',new=AsyncMock()):
  result=run(apply(upload()))
 assert result['result']=='eligible'
 assert db.candidates.docs[0]['cv_scan_status']=='Clean'
 assert Path(db.candidates.docs[0]['cv_path']).read_bytes()==PDF
 assert db.audit_logs.docs[0]['event']=='solver.cv.uploaded'
 assert 'cv_path' not in result
