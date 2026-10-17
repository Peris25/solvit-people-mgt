# Task 07 — My Profile & Employee Self-Service

Local implementation, 15 October 2026. Baseline: `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`. Tasks 01–06 are preserved. No production access, live data changes, migration, commit, push or deployment.

## Audit and requirements

Reviewed the existing EmployeeProfile, Staff Home/navigation, employee models/read/update endpoints, document storage/access, login/JWT/refresh/password-change flows and Task 02 first-login enforcement.

Authoritative documents reviewed locally:

| Source | Requirement | Result |
| --- | --- | --- |
| Developer Brief v1 §5.6, pp10–11 | Personal profile and permitted personal changes; employee requests, HR approves | Dedicated self-service route reuses EmployeeProfile. Typed, allowlisted personal changes remain pending until HR review. |
| Developer Brief §5.6 acceptance, p11 | Bank change is not applied until Finance approves | HR approval advances bank-containing requests to Pending_Finance. A separate Finance reviewer must approve before any requested fields are applied. |
| Developer Brief §5.6, p10; FRD §6.1/M01, p21 | Employee identity, employment details, manager, contacts; one employee source of truth | Canonical and legacy IDs resolve to the existing record; no employee duplication or roster hardcoding. Work email, department, role/level, salary, employment type/status and manager remain outside self-service requests. Existing stored staff IDs are displayed; missing IDs are not invented. |
| FRD §4.3, p17; Brief §7.1, p21 | Authentication/password security | Existing authenticated password-change endpoint and Task 02's stronger password policy, history checks, session invalidation and mandatory first-login gate are reused unchanged. |
| Brief §5.6a, pp11–12 | Per-file visibility; medical, disciplinary and salary documents HR only | Employee/manager access requires explicit visibility plus a non-confidential flag. Unclassified historical files default to HR only. Tenant, employee and file authorization applies to lists and direct downloads. |
| Handbook v2 §11a, p22; Task 07 instruction | Image use with employee knowledge; conservative placeholders without confirmed authorization | Initials/placeholders remain. My Profile does not return photo URLs or introduce photo publication/upload consent assumptions. |
| Brief §4, p6 | Employee base experience and separate Solver mobile experience | Employee-linked accounts use M01 self-service. Existing separate Solver functionality is preserved; this task does not grant Solver accounts access to the FTE database. |

The Brief contains a document-policy conflict: employee payslip/P9 download acceptance alongside a rule that salary documents are always HR only. This task follows the conservative confidentiality rule. Automatic Wingubox imports, an employee payslip distribution policy, document-centre expansion and self-service letter generation are not invented or claimed complete by Task 07.

## Findings and changes

1. **No dedicated My Profile route or personal edit workflow.** Staff Home linked to the generic employee URL. `/my-profile` now reuses EmployeeProfile, with dedicated own-profile/read/request APIs that never accept a client-selected employee. Navigation and Staff Home link to it. Missing/unlinked records show an actionable HR message; account security remains accessible.
2. **Changes require approval, not direct self-edit.** New `employee_profile_changes` records hold the requested patch, original values, submitter, status and review metadata. HR reviews personal changes; bank-related requests require HR then independent Finance. The entire mixed request waits for Finance. Employees cannot approve themselves; unrelated roles, forged identities, cross-tenant references and revoked access are denied.
3. **Stale/concurrent write protection.** Writes reuse the persistent integrity lock. A second pending request is rejected. Approval compares original values with the current record and uses a conditional update; intervening HR edits are not overwritten. A stale request can be rejected and resubmitted. Unexpected failure during final application leaves an explicit Applying state and persistent lock for controlled operator recovery.
4. **Permitted fields and compatibility.** Requests cover name/preferred name, personal contact details, DOB/gender, statutory identifiers, next of kin/emergency contact, education additions and bank/payment details. Types, lengths, email/phone/date formats and nested-field allowlists are enforced. Contact patches preserve saved fields; education additions retain existing entries. Known `bank_account` and `preferred_payment_method` aliases retain their existing storage format, with conflicting aliases blocked for HR reconciliation. Work/login email, account links, roles and reporting relationships are unchanged.
5. **Manager update restrictions were incomplete.** The general employee update endpoint now enforces M01 write scope and prevents managers changing department, role level, employment type/status or photo fields, in addition to existing salary/title/identity/reporting protections. HR retains authorized administration.
6. **Profile/history reads used only UUIDs and lacked tenant constraints on related collections.** Performance, leave, recognition, training, IDP and disciplinary queries now include canonical/native/storage aliases and tenant scope. My Profile returns an explicit personal-field projection and narrow IDP fields, omitting account secrets, internal risk/disciplinary data, raw notifications and unapproved photo URLs. Existing Task 01 manager-name fallback and department handling remain.
7. **Document endpoints ignored file visibility and used unscoped lookups.** Existing document routes now resolve tenant-scoped canonical/legacy ownership, apply per-file visibility to lists/downloads, reject ambiguous references and enforce private-root path containment. Downloads use attachment responses, no-store/nosniff headers and an audit entry. New uploads default to confidential HR-only access, with explicit HR sharing controls. HR removals soft-delete metadata and retain the original file for retention review, rather than physically deleting it. Existing files are not relabelled, moved or rewritten.
8. **UI reuse and security.** EmployeeProfile gains responsive personal-information cards, profile-change history, HR/Finance review inboxes, document states and an Account security tab. The existing password form is reused in optional embedded mode; its mandatory first-login default remains. Loading failures do not look like successful empty data, and account switching clears the previous profile. No new email/SMS or profile-event notification producer was introduced; reviewers use the profile review inbox.

## Modified files

- Backend: `backend/routes/employees.py`, `backend/routes/documents.py`, `backend/utils/staff_home.py`; new `backend/utils/profile_self_service.py`.
- Frontend: `frontend/src/App.js`, `frontend/src/components/Sidebar.js`, `frontend/src/components/RequiredPasswordChange.js`, `frontend/src/pages/EmployeeProfile.js`, `frontend/src/services/api.js`; new `frontend/src/components/ProfileChanges.js`.
- Tests: new `backend/tests/test_profile_self_service.py`, new `frontend/src/pages/MyProfile.test.js`; updated `backend/tests/test_employee_profile_display.py`, `backend/tests/test_password_change_enforcement.py`, `backend/tests/test_staff_home.py`, `frontend/src/pages/EmployeeDashboard.test.js`.
- This report. No dependency manifests or authentication implementation were changed.

## Verification

| Check | Result |
| --- | --- |
| Full backend (`python -m pytest backend/tests tests -q`, explicit disposable integration opt-in) | **786 passed**, zero failures/skips; six warnings, 134.23 seconds |
| Final profile safety recheck after persisting approval evidence before application | **47 passed**, including real MongoDB concurrency and interrupted-write cases |
| Full frontend (CRACO test, CI, `--watchAll=false --runInBand --detectOpenHandles`) | **103 passed**, 18 suites; 10.992 seconds |
| Strict CI build (`CI=true`) | Passed, compiled successfully |
| Normal production build (`CI=false`) | Passed, compiled successfully |
| Python compilation (`python -m compileall -q backend`) | Passed |
| Whitespace (`git diff --check`) | Passed; existing LF/CRLF notices are informational |

The initial authorization-related test-mock failure was corrected; the subsequent full suites passed. No assertion was weakened. The final approval-evidence adjustment was additionally verified by all 47 profile tests. Backend integration used an outbound-blocked API on `127.0.0.1:18089`, disposable MongoDB on `127.0.0.1:27089` and synthetic records only. No production account, credential, file or database was used.

Cleanup verified: both disposable suite databases were dropped and their absence checked; owned API/MongoDB processes stopped with neither test port left listening. Temporary MongoDB, Node and Python test runtimes were removed and their absence verified. HEAD remains the baseline commit; Task 07 files remain uncommitted.

Coverage includes own-record HTTP isolation, forged employee IDs, canonical/legacy IDs and foreign keys, safe personal projections, permitted/restricted fields, independent HR/Finance approval, self-approval denial, stale changes, duplicate pending requests, real MongoDB concurrent submissions, runtime revocations, document visibility/paths/download audit/retention, retained education/contact data, bank aliases, account switching and unchanged first-login/password regressions.

## Remaining policy decisions and staging prerequisites

1. HR must approve the requested personal changes and Finance must approve bank changes. This implementation does not treat developer access or this task as approval of employee data. Education self-service adds entries; corrections/removal of existing entries remain an HR operation. Conflicting legacy bank/education formats need HR review, not automatic conversion.
2. Provide valid account–employee links, configured M01/M10 permissions and distinct authorized reviewers. HR/Finance staff require another appropriate reviewer for their own requests. No new delegate role or self-approval exception was invented. Review queues are bounded to 200 pending records and personal history to 100 records; larger-volume pagination is future work.
3. HR must classify historical documents explicitly before employee/manager sharing. There is no automatic visibility migration. Salary/medical/disciplinary documents remain HR only even when a sharing value is supplied. Confirm the payslip/P9 policy conflict and individual photo authorizations before broadening access.
4. Verify persistent private `DOC_UPLOAD_ROOT`, filesystem/database encryption at rest, backup/retention, malware scanning and deployment routing so uploads cannot be served by nginx/static hosting. This task does not claim to deliver the full §5.6a document centre: bulk imports, Wingubox, document versioning/recycle-bin administration, virus scanning and 20MB/XLSX support remain separate work; the existing 10MB/type limits remain. No historical file was deleted in development.
5. No migration or production index installation is needed for backward-compatible reads. The change-request collection is created naturally only when the local/staging workflow is used. Existing Task 02 integrity/index rollout prerequisites still apply. Every application profile-request write uses the existing lock; direct database writers must follow the same controlled process.
6. **Interrupted application recovery:** stop/quiesce all writers and follow `docs/employee-integrity-rollout.md` before touching a persistent lock. Review Applying requests against `employee_storage_id`, the saved before-values, requested changes, HR/Finance review evidence and audit records. If the employee patch was applied, complete the request/audit only after operator verification; if not, return it to a reviewed state only after proving no write is still running. Mixed/unexplained states require manual reconciliation. Do not expire/delete locks automatically or blindly replay a bank change. This task does not run any recovery action.
7. HR UAT on an approved staging dataset: ordinary employee, own-manager and unrelated-manager requests, HR/Finance independent review, HR/Finance own requests, revoked permissions, unlinked/legacy accounts, mobile layouts, protected document links, stale changes and password/session invalidation. Confirm actual contract/document policy and at-rest protection before production acceptance.

Ready for controlled staging/UAT after these environment prerequisites; this report does not claim production deployment, data reconciliation or final HR policy approval.
