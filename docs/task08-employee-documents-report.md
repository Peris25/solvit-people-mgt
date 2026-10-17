# Task 08 — Employee Document Centre

Local implementation, 15 October 2026. Baseline commit: `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`; all uncommitted Task 07 work is preserved. No production access, live record changes, migration, index installation, commit, push or deployment.

## Audit and reference alignment

Reviewed the existing employee-document routes/storage, My Profile Documents tab, Policy Library file routes, employee identity/access helpers, Staff Home, navigation and Task 07 change approvals. The Developer Brief §5.6/§5.6a (PDF pp10–12) supplies the central document page, 20 MB formats, HR assignment, configurable categories, explicit visibility, scanning and audit requirements. FRD §4.3 (p17) supplies existing session protections; its earlier 10 MB upload guidance is superseded here by the explicit Task 08 instruction and Brief. Handbook v2's privacy/image provisions remain; no photographs are published or consent inferred.

Findings:

- The only employee file UI was embedded in EmployeeProfile; Staff Home conflated documents with the Policy Library.
- Uploads used a 10 MB limit, lacked XLSX/content validation/scanning, and contained a MIME condition that could accept a mismatched declared type.
- Task 07 correctly introduced conservative file visibility, canonical ownership, private-root download checks and retained original files on HR removal. Those protections are extended, not replaced.
- Native legacy document identifiers were not fully resolved by the shared linked-record lookup.
- Policy downloads trusted a stored path without checking their own root, and policy metadata updates could accept `file_url`. This could undermine separation between public-facing policies and private employee files.

## Implemented

1. **Dedicated Documents page:** `/documents`, Staff Home link and navigation. Employees load `/api/documents/me` without choosing an employee ID. HR can select an existing saved employee through EmployeePicker, then upload/manage assigned files. My Profile and the page reuse one `EmployeeDocuments` component. Policy Library has a separate link and store.
2. **Authorized list/download:** name/title, category, upload date and availability/effective/expiry status, with loading, empty, denied and retry states. Downloads use the authenticated API as a blob, an attachment response and a temporary local download URL that is revoked. Private storage paths are never returned. Account/employee switching clears old results and ignores stale responses.
3. **20 MB per file:** PDF, JPG/JPEG, PNG, DOCX and XLSX. Backend checks filenames, extension, declared MIME, actual signatures/container structure, non-empty content and bounded chunked reads. Images are verified with the existing Pillow dependency and pixel bounds. Office files are inspected without extraction; malformed archives, traversal names, excessive expansion, duplicate entries, encrypted entries, macros, embedded objects and external relationships are rejected. No new package dependency was added.
4. **Fail-closed malware scanning:** ClamAV-compatible INSTREAM adapter using `DOC_SCANNER_HOST` and optional `DOC_SCANNER_PORT` (3310). A positive clean result is required before any new file/document is saved. Malware rejection returns 422; missing/unavailable/error verdicts return 503. No shell invocation, user-selected scanner command, cloud document upload or production scan bypass exists.
5. **Private storage:** existing `DOC_UPLOAD_ROOT` is reused. Random immutable filenames live beneath the canonical employee storage ID, with exclusive file creation, containment checks, POSIX private modes for new directories/files and no client-controlled disk path. Existing stored files are not moved or renamed.
6. **HR classification and changes:** uploads default to confidential HR only. Explicit sharing remains required; medical, disciplinary and salary/payslip/P9 records remain HR only. HR can update title, category, visibility/confidentiality and issue/effective/expiry dates. Ownership and storage paths cannot be changed through metadata. A sensitive classification cannot be removed merely by renaming its category.
7. **Audit/integrity:** uploads, downloads, metadata changes and HR removals retain actor/time/employee/document audit records. Metadata history stores permitted before/after fields. Application writes use the existing persistent integrity lock. New uploads/metadata edits remain `Pending_Audit` until their audit succeeds; staff cannot list/download incomplete publications. Unexpected interrupted writes fail closed for operator review. HR removal remains soft deletion; original files are retained.
8. **Authorization:** tenant-scoped canonical/storage/native references, employee/file checks on lists/downloads, HR-only writes, scoped audit responses, runtime M01 restrictions and direct-download denial for exited/suspended/terminated employee views. An ID supplied in a query cannot retarget the own-documents endpoint. First-login password-change enforcement also covers the new endpoints.
9. **Policy-store boundary:** policy file reads are tenant-scoped and confined to `POLICY_UPLOAD_ROOT`. Disk paths are omitted from policy responses, file-path/ownership edits are rejected, and policy replacements retain old file bytes under new random names. Existing policy acknowledgements remain separate from employee documents.

## Modified files for Task 08

- Backend: `backend/routes/documents.py`, `backend/routes/policies.py`, `backend/utils/employee_access.py`, `backend/utils/staff_home.py`; new `backend/utils/document_uploads.py`.
- Frontend: new `frontend/src/pages/Documents.js`, new shared `frontend/src/components/EmployeeDocuments.js`; updated `frontend/src/pages/EmployeeProfile.js`, `frontend/src/App.js`, `frontend/src/components/Sidebar.js`, `frontend/src/services/api.js`.
- Tests: new `backend/tests/test_employee_documents.py`, new `frontend/src/pages/Documents.test.js`; updated `backend/tests/test_iteration_9.py`, `backend/tests/test_password_change_enforcement.py`, `backend/tests/test_staff_home.py`, `frontend/src/pages/EmployeeDashboard.test.js`.
- Guarded synthetic integration fixture: `backend/scripts/local_test_server.py` substitutes only the malware verdict in its explicitly localhost-only, outbound-blocked process. Application content validation remains real. Production application code has no environment-based scan bypass.
- This report. Earlier Task 07 modified/new files remain intact and uncommitted.

## Tests

| Check | Result |
| --- | --- |
| Full backend (`python -m pytest backend/tests tests -q`, explicit disposable integration opt-in) | **831 passed**, zero failures/skips; six warnings, 124.41 seconds |
| Final document recheck after adding missing-business-ID/missing-file compatibility | **42 passed**, including the final additional legacy regression |
| Full frontend (CRACO, CI, `--watchAll=false --runInBand --detectOpenHandles`) | **112 passed**, 19 suites; 10.749 seconds |
| Strict CI build (`CI=true`) | Passed, compiled successfully |
| Normal production build (`CI=false`) | Passed, compiled successfully |
| Python compilation (`python -m compileall -q backend`) | Passed |
| Whitespace (`git diff --check`) | Passed; existing LF/CRLF conversion notices are informational |
| Real XLSX compatibility | A generated openpyxl workbook passed validation |

The first complete backend run also passed 828 tests; further security cases were then added. The final legacy fallback fix was verified by the complete 42-test document-focused suite after the 831-test full run. Integration used only the guarded localhost API and disposable MongoDB with synthetic records; no production or real scanner service was contacted.

Cleanup verified: both disposable suite databases were removed and their absence checked. Owned API/MongoDB processes stopped, neither test port remained listening, and temporary MongoDB/Node/Python test runtimes were removed with absence verified. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`; all Task 07–08 changes remain uncommitted.

Coverage includes valid types, MIME/signature spoofing, unsafe filenames/ZIP entries, exact 20 MB and oversized/empty files, scanner protocol/positive/infected/error/missing configuration, no writes on scan failure, HR assignment, immutable ownership, employee isolation, authenticated HTTP download bytes/headers, audit records, legacy IDs, restricted classification, publication/audit failure, account switching, metadata management, no private path in responses, Policy Library isolation and Tasks 01–07 regressions.

## Storage, policy and staging prerequisites

- **Scanner required before new uploads work:** configure a private trusted ClamAV service, keep signatures current, set stream limits to accept at least 20 MB and configure host/port. Test clean, EICAR and unavailable-service behaviour in isolated staging. Local integration uses a synthetic verdict; no real staging/production scanner was contacted or certified. Existing authorized legacy documents remain readable under Task 07 rules; they were not automatically rescanned or relabelled.
- **Persistent private storage:** set `DOC_UPLOAD_ROOT` outside any web/static root, mount persistent storage, enforce service-account-only ACLs (particularly Windows ACLs), encrypt at rest, back up metadata and bytes together, and test restoration. Keep `POLICY_UPLOAD_ROOT` physically separate; do not serve either private document directories through nginx/static aliases. The repository's current Render manifest does not establish a persistent employee-document disk or scanner service; hosting operators must configure these explicitly.
- **Ingress capacity:** configure proxy/body/time limits for a 20 MB file plus multipart overhead, bounded multipart spooling/temp storage and per-user request limits. The application validates bounded file reads; reverse-proxy request-size and disk-capacity controls remain deployment prerequisites. Scanning has a 60-second deadline. Office security checks deliberately reject embedded/external content; HR can supply an approved PDF where an Office file is rejected.
- **HR sharing decisions:** classify each record explicitly; historical missing visibility/confidentiality is HR only. The Brief's payslip/P9 self-download goal conflicts with its salary-document HR-only rule. Task 07's stricter rule remains until HR approves a specific distribution policy. Contracts/ID documents are not automatically shared; no roster/file migration or filename-based assignment occurred.
- **Retention/recovery:** no purge job, migration or automatic lock expiry was added. Confirm retention, recycle-bin administration and existing orphan-file reconciliation. For `Pending_Audit` or a persistent lock, quiesce writers and follow `docs/employee-integrity-rollout.md`; verify file, employee ownership, scanner/audit evidence and intended visibility before an operator completes or reverses an interrupted operation. Do not blindly mark files Ready or delete locks. A database/filesystem transaction or durable outbox is not claimed.
- **Bounded scope:** this employee-centre increment does not implement automatic Wingubox payslip/P9 imports, SharePoint/bulk ZIP imports, phone-photo conversion, full document-version/recycle-bin administration, required-document checklists, requested employee uploads, generated letters, expiry-reminder jobs or a separate Solver document ownership model. Those broader Brief features require their own approved workflows/data mapping. No Solver record is converted to or duplicated as an employee.
- **HR UAT:** test employee, unrelated employee, direct manager, HR, Finance, IT, revoked role, unlinked/system account and exited employee; approved/unapproved legacy files; HR assignment and classification; scan failures; 20 MB uploads; private download headers; mobile layouts; storage persistence and audit recovery. Existing Task 02 database/index prerequisites and Task 07 profile/bank approvals remain unchanged. No production index was installed.

Local implementation is suitable for controlled staging/UAT once private persistent storage and the scanner are configured. It is not a claim of production deployment or final HR policy acceptance.
