# Task 13 - Employee Benefits & Payroll Information

## Outcome and boundaries

Implemented a local benefits core in the existing React/FastAPI/MongoDB application: HR-configured medical/accident schemes, explicit eligibility, employee enrolment/change requests, HR review, private membership history, Finance-only approved premium records, and Staff Home/Notification Centre integration. Reused My Profile and the private Document Centre. No payroll engine, payment, statutory deduction, bank API, insurer submission or Wingubox import was invented.

Tasks 01-11 and the Task 12 audit are preserved, including all pre-existing uncommitted changes. No production/staging access, live data change, migration, production index installation, commit, push or deployment occurred. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`.

This is not a claim that every item in Developer Brief section 5.15 is complete. Integration/configuration gaps are listed below, especially actual insurance terms, insurer exports/removals/reminders and payroll document publication.

## Reference review and traceability

Reviewed the three authoritative PDFs in `docs/reference/`; references below use PDF page numbers. Embedded document instructions are requirements evidence, not permission to seed data, connect to providers or deploy.

| Source | Requirement | Result |
| --- | --- | --- |
| Developer Brief v1, section 5.15, p17 | Group medical/accident schemes, insurer/policy, cover levels, policy dates, worker-type/start-date eligibility | Implemented explicit HR-managed draft/published/archived schemes. No defaults assume an insurer, covered employee, dependant entitlement or premium. Publication requires the recorded HR/Finance policy approval reference. |
| Brief section 5.15 | Employee cover confirmation, dependant identity evidence, accident beneficiary percentages totaling 100 | Implemented structured requests with bounded fields, dates, eligibility and share validation. Supporting documents must already exist in the protected Document Centre under the same employee; existing HR upload/sharing restrictions remain. |
| Brief section 5.15 | Marriage/birth/adoption/dependant-leaving changes require evidence and HR approval | Implemented documented reasons and evidence checks; pending changes do not replace approved membership. HR cannot approve their own request. |
| Brief section 5.15 | My cover/dependants, insurer contacts and claim guidance; no claims or diagnoses stored | Implemented own membership history and saved policy snapshots/contacts/instructions. No claims/diagnosis fields or medical upload pathway added. No automated insurer confirmation is claimed. |
| Brief section 5.15 | HR/Finance participation oversight; premiums Finance-only; dependant details HR-only | HR reviews membership; Finance gets participation status without households or HR decision notes. Only the employee personally and authorized HR see household data, reconciling the same section's explicit My dependants requirement. Managers receive no team benefits access. Premium values and their revision history are stored separately and excluded from HR-readable audit metadata. |
| Brief sections 5.6 / 5.6a, pp10-12; integration table p22 | Own payslips/P9 via Document Centre, imported from Wingubox; bank changes require Finance approval | Existing Document Centre and HR-then-Finance profile-change controls preserved. No payslip/P9 access restriction was relaxed. Wingubox import/release remains pending approved integration and sharing policy. |
| Brief Staff Home / access matrix, pp7-8 | Employee quick actions; Finance approvals and payroll-related information | Added Benefits & payroll information links in navigation, My Profile and Staff Home; eligible enrolment prompts and recipient-scoped membership notifications. No private amounts or household information in previews. |
| Handbook v2, sections 4.1 / 4.5, p6 | Contract controls remuneration; monthly salary; no automatic annual increase | No salary derived from a band or performance score for self-service. Pending salary reviews are not approved payroll information and are no longer emailed as approved outcomes. No salary/contract record is updated by this task. |
| Handbook v2, section 4.6, p7 | Optional Britam Tier II pension; terms/enrolment from HR | Added clearly labelled information/referral to HR; no invented contribution rates, membership, eligibility or pension workflow. Existing statutory figures were not treated as authority for new calculations. |
| FRD M10/M12, pp33-34 | Compensation/Finance gate, approved rewards, Finance-controlled inputs | Existing module extended with permission override enforcement, tenant isolation, bounded proposals and audit-before-write controls. No new approval/payment engine or bonus formula was introduced. Missing source worksheets/workflow details remain prerequisites. |

## Audit findings and changes

- No benefits scheme/membership module or Wingubox import was found in the existing code. Employee self-service already provides bank fields and change requests through Task 07. Task 08's document metadata, scanner, download audit and owner checks were available for reuse.
- The old salary-review POST accepted arbitrary fields and emailed the employee immediately while storing `Pending_Finance_Approval`. It now validates an allowlist, resolves the saved employee within tenant, records a proposal audit and sends no premature outcome email. It never applies the proposed salary.
- Existing compensation endpoints hardcoded the Solvit tenant and relied on role checks without honoring M10 overrides. Reads/writes now use current-tenant scoping and configured module permission, with original role boundaries retained. Salary-review Finance responses exclude unrelated raw HR fields. Numeric performance scores are redacted from the Finance bonus response; pay/bonus eligibility information remains within the existing Finance workflow.
- Pay-band updates now validate ordered numeric ranges, resolve canonical/legacy record identifiers within tenant and audit before mutation under the integrity lock. Existing Finance gate confirmations also use the lock/audit and cannot forge tenant, record or actor metadata. No gate formula/payment action changed.
- Benefits self-service derives identity from the authenticated account; supplied employee, manager, status, premium or medical fields are rejected. Missing, inactive/exited or board-only employee links cannot enrol. Approved policy worker-type and service-date rules control visibility; no roster is hardcoded.
- New schemes are not published automatically. Published policy terms become immutable (even after archiving); changed terms require a replacement scheme. Membership retains a policy snapshot. Draft edits and archive operations are audited.
- One pending membership per employee/scheme is enforced inside the existing cross-worker persistent integrity lock. Changes require a supported reason and an authorized same-employee supporting file. Dependant evidence must be available, non-restricted, non-deleted and visible through existing document permissions. Future births and invalid/duplicate dependant entries are rejected. Accident shares must be finite, positive and total 100 percent.
- HR verifies eligibility and evidence again at approval. Managers and Finance cannot approve membership. Decisions cannot be replayed, and self-approval is denied. Previous approvals remain immutable; new approvals reference predecessors and personal history marks superseded entries as historical. Local HR approval is explicitly not proof of insurer-confirmed coverage.
- Finance-only monthly premium entries record manually verified amounts and approval references; revisions preserve prior values in the private financial history. Premium amounts are not inferred or calculated and are absent from employee/HR scheme DTOs, notifications and HR-readable audit metadata.
- Benefit request/decision notifications are recipient-scoped with deterministic event keys. Generic previews contain no compensation, bank, insurer-member or household details. Staff Home prompts derive from actual approved eligible schemes and saved deadlines; reads create no membership records.
- Private documents are selected through existing authenticated APIs; no file contents, storage paths or unrestricted URLs are exposed by the benefits APIs. Required files continue to use HR upload and sharing approval. A link to Document Centre does not grant payslip or medical-file access.

## Files modified for Task 13

- `backend/utils/benefits.py` (new): scheme/eligibility, membership approvals/history, evidence authorization, premium isolation, audit and notification helpers.
- `backend/routes/benefits.py` (new), `backend/server.py`: authenticated benefits routes and registration.
- `backend/routes/compensation.py`: scoped/permission-aware reads, validated audited financial writes, pending salary-review confidentiality and Finance projections.
- `backend/utils/staff_home.py`, `backend/utils/notification_centre.py`: own enrolment actions, quick link, generic Benefits events and authorized links.
- `backend/tests/test_benefits_payroll.py` (new): benefits and compensation security/workflow regressions, including real local MongoDB concurrency.
- `backend/tests/test_password_change_enforcement.py`: all nine new benefits routes included in the mandatory password-change gate coverage.
- `backend/tests/test_profile_self_service.py`, `backend/tests/test_staff_home.py`: add empty benefit collections to synthetic fixtures; preserve existing bank-approval and dashboard assertions.
- `backend/tests/test_iteration_18.py`: replace the obsolete immediate salary-outcome email expectation with a pending/no-email regression.
- `frontend/src/pages/Benefits.js`, `frontend/src/pages/Benefits.test.js` (new): responsive personal/admin views, structured enrolment/change evidence, HR decisions, Finance-only premium inputs, safe states and account-switch privacy tests.
- `frontend/src/App.js`, `frontend/src/components/Sidebar.js`, `frontend/src/pages/EmployeeProfile.js`: route and navigation integration.
- `frontend/src/services/api.js`: benefits calls.
- `docs/task13-benefits-payroll-report.md`: this report.

Other working-tree changes are from earlier tasks and are preserved. No dependency manifest or existing document-sharing permission changed.

## Test results

Final verified Task 13 results: **1,036 backend tests passed** (6 warnings, 135.11 seconds), including all 56 Task 13 regressions; **146 frontend tests passed** across 23 suites. Strict CI and normal production builds compiled successfully. Python compilation, `git diff --check` and new-file whitespace checks passed. All tests used synthetic local data.

Tests used synthetic fixtures and an outbound-blocked disposable MongoDB/API on localhost ports 27089/18089. Real MongoDB tests verify duplicate concurrent enrolment prevention and notification payload preservation. Existing document integration tests retain the Task 08 synthetic scanner harness; production scanning remains fail-closed. Tests did not use real employee insurance, compensation, bank details or provider credentials.

## Policy questions and staging prerequisites

1. HR and Finance must supply approved insurer/policy details, covered worker types, service-date rules, cover levels, dependant limits, policy periods, enrolment deadlines and claim/contact instructions. No real schemes or memberships were seeded. The publication reference records an administrative attestation; this is not a new two-party digital scheme-approval workflow.
2. Confirm the privacy interpretation of My dependants versus dependant details HR-only. The implementation permits the employee's own details and authorized HR, while denying manager access and excluding household data from Finance oversight. It stores enrolment identities/evidence references, never medical claims or diagnoses. Review lawful basis, retention and private backup/storage access in staging.
3. Employee uploads were not added. Dependants/change evidence must already be HR-uploaded and explicitly shared under Task 08. Confirm whether a future restricted employee upload channel is authorized before enabling it. Member cards/benefit documents remain subject to existing category and sharing rules; nothing is automatically published.
4. Payslip/P9 delivery remains a gap: the Brief authorizes self-service, but existing Task 07/08 safeguards deliberately restrict those categories. An approved payroll-document release policy and verified Wingubox API/export format, identity mapping, period/idempotency rules and private scanning/storage arrangement are required. No existing payroll data was inferred, exposed or imported. Finance was not given blanket access to employee documents.
5. Monthly insurer member-schedule exports, insurer delivery, automatic removal/submission on effective exit dates and renewal/missing-document/deadline reminder automation from the full section 5.15 are not implemented in this focused core. The insurer format, effective coverage rules and integration are not supplied. Exited employees cannot use self-service or enrol; HR/Finance historical views warn that insurer removal requires confirmation. Do not use these local records as an insurer-confirmed active membership list.
6. Optional Britam pension terms/enrolment remain with HR. No pension contribution or statutory deduction engine is added. Handbook remuneration provisions do not establish actual individual salary values or authorize automated bank transfers.
7. Existing M10 bonus calculator rates differ from the FRD's two-tier worksheet descriptions. Its formulas and historical scores were deliberately not rewritten. The referenced Pay Banding Guide, Bonus Calculation Worksheet and Salary Review/Reward Approval workflow artifacts were not supplied as standalone authoritative files. Do not treat the legacy calculator or a pending salary proposal as approved payroll; reconcile policy/gates and define approved outcome release before any payroll integration. This task does not implement the missing end-to-end salary-review approval/application workflow.
8. Verify role/employee/tenant isolation, HR self-approval prohibition, archived/replacement policies, actual manager/employee account links, first-login enforcement, explicit M01/M10 overrides, supporting-file permissions and generic notification previews in isolated staging. No new email/SMS delivery was added.
9. No migration is required for the additive benefits collections/fields. No database index was installed. Existing Task 02 index prerequisites remain; review future benefit lookup/uniqueness indexes before approved rollout. All application writers must use the same API version/lock; direct database writers bypass application guards.
10. Mutations, audit and notifications are not MongoDB transactions. Unexpected interrupted writes intentionally retain the persistent integrity lock. Quiesce writers, inspect data/audit state and follow `docs/employee-integrity-rollout.md` before operator recovery; do not remove an active writer's lock or blindly replay sensitive requests.

The implemented core is intended for isolated staging validation after passing checks and HR configuration. Full payroll/insurance operations and policy approval are not claimed.

The final report/cleanup step was interrupted by the next task and completed during Task 14 closure: all disposable suite databases and test runtime directories were removed, synthetic API/MongoDB processes stopped, and ports 18089/27089 confirmed closed. See `docs/task14-audit-reporting-report.md`. No production service was involved.
