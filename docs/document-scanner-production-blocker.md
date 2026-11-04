# Document uploads blocked: scanner not configured

The reported production response is HTTP 503: `Document scanning is not configured; upload was not saved`. This exact branch in `backend/utils/document_uploads.py` means `DOC_SCANNER_HOST` is absent/empty. It is not a rejection of the employee's ID and not evidence of malware. `backend/routes/documents.py` calls scanning before persisting file bytes/metadata.

The shared frontend interceptor converts 5xx errors into resolved responses with an `error` string. EmployeeDocuments previously replaced that useful detail with Upload was not confirmed. It now preserves the scanner error in the open dialog and retains the selected file. No security checks were disabled.

## Required hosting work before uploads can be enabled

1. Provision or identify a trusted private ClamAV-compatible daemon supporting TCP INSTREAM. Recommended deployment: a separate private Render service in the backend's workspace/region, with network access limited to trusted services. Do not expose raw ClamAV TCP to the internet or use a public file-submission service for employee IDs.
2. Size for ClamAV's documented minimum/recommended memory (approximately 3–4 GiB); a small 512 MB application instance is unsuitable for hosting the daemon alongside the API. Approve the additional hosting cost before creating the service. Keep signatures current and ensure the scanner is ready before accepting uploads.
3. Set backend `DOC_SCANNER_HOST` to the scanner's internal hostname (without scheme/path) and `DOC_SCANNER_PORT=3310` unless the daemon is configured on a different port. The implementation uses plain TCP on a trusted private network, expects the exact clean verdict and fails closed on missing configuration, connection errors, timeouts or indeterminate results.
4. Verify the backend's private persistent document storage. If its persistent disk is mounted at `/var/data`, an example is `DOC_UPLOAD_ROOT=/var/data/employee_docs`; do not move existing files without a separately reviewed storage plan. Keep paths outside public/static roots and confirm durable storage/backup permissions.
5. Verify the request-size limit for the promised 20 MB files. The code's default `MAX_BODY_BYTES=6291456` is only 6 MiB; an example limit of `23068672` accommodates 20 MiB plus multipart overhead. Confirm actual proxy limits and scanner StreamMaxLength as well. This is a separate size prerequisite, not the cause of the reported small-file error.
6. Validate a synthetic clean document, an isolated EICAR scanner check and unavailable-scanner behavior in a controlled test environment; then verify authorized upload/download and audit records. Do not use a real employee ID for infrastructure testing.

Official references: https://render.com/docs/private-services , https://render.com/docs/private-network , https://docs.clamav.net/manual/Installing/Docker.html .

## Delivered code fix

Files: `frontend/src/components/EmployeeDocuments.js`, `frontend/src/pages/Documents.test.js`, and this report. All 323 frontend tests passed across 44 suites, including the actual resolved-503 response shape. Strict CI and normal production builds and whitespace checks passed. No backend, production configuration, storage or employee data was changed. The scanner remains an unresolved production infrastructure prerequisite.
