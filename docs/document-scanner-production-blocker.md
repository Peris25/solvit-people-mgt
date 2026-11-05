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

The initial frontend fix changed `frontend/src/components/EmployeeDocuments.js`, `frontend/src/pages/Documents.test.js`, and this report. All 323 frontend tests passed across 44 suites, including the actual resolved-503 response shape. Strict CI and normal production builds and whitespace checks passed. The infrastructure work below follows that initial release.

## Hosting follow-up — 5 November 2026

- User approved a private Oregon Render scanner at $25/month (1 CPU, 2 GB RAM), and a 5 GB backend disk at $1.25/month. Total additional approved cost is $26.25/month before taxes.
- `solvit-document-scanner`, using the official `clamav/clamav:1.4` image, deployed successfully and updated its signatures. Initial memory chart was approximately 45% of 2 GB. A user-run check from the People backend returned `PONG` over private TCP port 3310. This verifies reachability, not an end-to-end malware verdict or sustained memory stability.
- The scanner was configured with `CLAMD_CONF_ConcurrentDatabaseReload=no`, `FRESHCLAM_CONF_TestDatabases=no`, `CLAMD_CONF_MaxThreads=1`, and `CLAMD_CONF_MaxQueue=4`. Verify effective daemon configuration and stability through a signature reload: the 2 GB plan is below ClamAV's documented minimum/recommendation and remains a capacity risk. No file-type detection was deliberately disabled. Uploads remain fail-closed.
- Before disk attachment, the user ran the supplied read-only count against configured document, CV and leave-evidence roots: all returned zero files. This does not prove that older database attachment references have corresponding files or reconcile other storage roots.
- A 5 GB backend disk is attached at `/var/data`. The saved backend configuration uses `DOC_UPLOAD_ROOT=/var/data/employee_docs`, `CV_UPLOAD_ROOT=/var/data/solver_cvs`, `LEAVE_EVIDENCE_ROOT=/var/data/leave_evidence`, `DOC_SCANNER_HOST=solvit-document-scanner`, `DOC_SCANNER_PORT=3310`, and `MAX_BODY_BYTES=23068672`. Configuration deployment is being verified. Other environment values, employee records and database data were not changed.
- A disk prevents horizontal scaling and zero-downtime backend deployments on Render. Render advertises daily disk snapshots with seven-day retention; separately verify restore and backup procedures.

## Solver CV security follow-up

The public job-application CV path previously wrote files without calling the existing scanner. `backend/routes/solver_intake.py` now bounds the read to the 5 MB limit plus one byte, checks extension/content agreement, validates PDF/OOXML structure, and requires a clean scanner verdict before storing the file or application. New CVs use exclusive private file creation and scan-status metadata with a metadata-only audit event. Existing CV records are not rewritten or retrospectively marked clean.

`backend/tests/test_solver_cv_scanning.py` adds nine regression cases covering clean uploads, unavailable scanning, malware rejection, size/type validation, and absence of candidate/file writes after scan failure. Full backend validation: **1,482 passed, 321 skipped, five warnings**. Python compilation and whitespace checks passed. No new frontend changes in this follow-up.

Render subsequently confirmed the environment-configuration deployment succeeded, followed by the automatic deployment of backend commit `99ad240` (Live, duration 1m 52s). The working tree was clean after that release. A read-only user-run check was supplied to exercise the actual application scanner client and verify the disk mount/configured roots; its result is pending.

Outstanding live verification: effective scanner memory configuration, a synthetic clean INSTREAM verdict, authorized document upload/download and its audit trail, public CV submission, and survival of stored synthetic files across a subsequent backend restart. No real ID or applicant CV should be used for infrastructure tests. Keep the scanner private, monitor memory and signature freshness, and never bypass scanning to restore availability.

## Mandatory applicant CV — 5 November 2026

The user subsequently supplied a successful live check: the application scanner client returned CLEAN, `/var/data` was mounted, and both document/CV roots matched their persistent paths. The user also confirmed a successful portal document upload. Authorized downloads, applicant CV submission, restart persistence and sustained scanner capacity remain separate verification items.

New vacancy applications now require a CV. The React form labels the field as required, applies browser validation and blocks submissions without a valid selected file. Invalid replacement files clear an earlier selection. The FastAPI multipart schema requires the CV, and an explicit empty-filename check protects the application handler. Existing file-type, 5 MB, private-storage and malware-scan protections remain. Historical applications without CVs are preserved; no CV is invented or backfilled. The standalone assessment questionnaire is unchanged.

Changed files: `backend/routes/solver_intake.py`, `backend/tests/test_solver_cv_scanning.py`, `frontend/src/pages/PublicSolverApply.js`, `frontend/src/pages/PublicSolverApply.test.js`, and this report. Regression suites: **1,485 backend passed, 321 skipped, five existing warnings; 325 frontend passed across 45 suites**. Tests cover direct HTTP requests omitting CVs, blank filenames, UI submission without a CV and invalid replacement selection, alongside the existing clean-scanned submission coverage.
