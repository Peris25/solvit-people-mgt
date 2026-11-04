# Private HR payroll Excel uploads — 4 November 2026

HR requested a file-upload facility in Benefits & payroll information, not an
employee-data import. HR chooses the workbook to retain there later. No live file
is uploaded as part of this implementation.

The HR-only Payroll files section supports explicit upload, listing the latest
100 files and authenticated downloads. XLSX workbooks up to 5 MB are accepted;
the smaller attachment limit fits the existing default request-body allowance.
XLS/XLSM and other formats are not accepted. No workbook rows are imported or
evaluated, and no employee, salary, banking, benefit or balance record is changed.

Files reuse DOC_UPLOAD_ROOT, document content validation, ClamAV scanning,
employee_documents metadata and document_audit. They have a dedicated document
kind, no employee owner, permanent HR-only visibility and confidential/restricted
flags. Ordinary employee document endpoints cannot expose them. HR Admin,
HR Manager and General Manager must retain their existing M10 and M01 grants;
Finance, IT Admin, managers and employees receive no new access.

Storage uses tenant-separated private directories and random exclusive filenames.
No storage paths or unrestricted URLs are returned. Downloads check tenant,
document kind, clean scan, publication state and path containment, and are audited.
Publication becomes Ready only after upload audit succeeds. Interrupted audit
writes remain unavailable pending controlled integrity-lock recovery. No delete,
share, overwrite, payroll calculation or automatic import action is added.

Validation: 1,409 backend tests passed; 321 existing environment-dependent tests
skipped. All 305 frontend tests passed in 42 suites. Strict and normal production
builds, Python compilation and whitespace checks passed.

Operational prerequisites: existing DOC_UPLOAD_ROOT must be on private persistent
storage; DOC_SCANNER_HOST/PORT must identify an available clean-verdict scanner.
Uploads fail closed with HTTP 503 if scanning is unavailable. Production scanner
connectivity and real-file acceptance are not tested by uploading confidential
HR files during development. No migrations, new dependencies or credentials are
required. No live workbook or employee records were changed.
