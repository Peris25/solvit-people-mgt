# Task 09 — onboarding and offboarding

Local implementation. No production access, live-data changes, migrations, indexes, commits, pushes or deployment. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`; existing Tasks 01–08 work is preserved.

## Requirements reviewed

Read the locally supplied Developer Brief §5.8 (PDF p13), §5.11 (p14), document requirements §5.6a (pp11–13), FRD §§5.1–5.2 and onboarding module M04, and Employee Handbook v2 §10 (pp18–20). Documents are reference material, not operational authorization to change employee records.

- Onboarding: reuse the existing 19-item checklist, with corrected owner roles and date offsets for newly created items; add assigned 30/60/90-day check-ins, asset issuance, Finance payroll verification and HR document verification. Existing saved tasks and completion evidence remain intact.
- Offboarding: reuse the seven ET tasks and Form 23's 23 clearance fields, with an explicit manager handover verification item. These 31 tracked items cover IT, Admin/HR, Finance and manager responsibilities without introducing a second clearance form.
- Handbook §10.1: probation notice is 14 calendar days; confirmed employees' notice depends on their contracts (minimum 30 days). This change requires HR to confirm the last working day and record an authorization reference; it does not invent contract terms or calculate a notice date from job title alone.
- Developer Brief §5.11: separately authorized access revocation becomes eligible at 17:00 EAT on the confirmed last day. An existing APScheduler job checks every 60 seconds and catches up after downtime. Pending clearance does **not** postpone authorized login revocation. Archival remains blocked until clearance and active-report reassignment are complete.
- Handbook §10.3/10.4 has differing terminal-dues timing language (before last day for redundancy versus within seven days generally). No automated payment withholding, deductions, settlement or payroll calculations were introduced. HR/Finance must confirm the applicable process.

## Audit findings and implemented changes

1. Employee onboarding GET previously created records, ignored template day offsets and allowed updates based on employee scope alone. Reads are now read-only; HR initiation and existing automation share serialized, canonical/legacy-ID-aware, retry-safe creation. Missing start dates require HR correction rather than invented dates.
2. Existing automation independently inserted duplicate onboarding and exit tasks. Both paths now reuse the checklist creators under the existing persistent integrity lock. Partial legacy onboarding checklists can resume without resetting completed items or duplicating task keys.
3. The tracker previously displayed aggregate HR cards only. The existing `/onboarding` screen now shows authorized employee/manager/HR/IT/Finance checklists, responsibility, due date, progress, completion controls and loading/error/empty states. HR can initiate either workflow using existing employee selection. No new employee or account is created by these endpoints.
4. Responsibility is enforced server-side. Employees complete their own employee-assigned items; current managers complete direct-report manager items; assigned IT and Finance roles have task-only access; HR retains authorized administration. Restricted board records retain conservative access. Scoped DTOs omit free-text notes and private employee fields. Completed items cannot be reopened through alternate task routes, and completed offboarding is immutable.
5. Exit initiation records HR authorization and a confirmed last day. It preserves employee identity, manager assignment, balances, historical documents and accounts. It does not deactivate access immediately. HR cannot initiate or authorize their own exit through these operations.
6. Completion requires all clearance items, resolved active direct reports, the time cutoff and exactly one eligible linked account. Authorization is audited before session invalidation/account deactivation. Existing access and refresh tokens fail the existing database-backed active-account/session checks. Historical employee records are archived, never deleted.
7. HR may separately pre-authorize scheduled deactivation. The scheduler rechecks the authorizer's current active account, HR role and module permission. It revokes access at/after the cutoff even with unfinished clearance, preserves the Exiting record, and sends a deduplicated review notification if archival is blocked. Ineligible or ambiguous accounts are never guessed or automatically merged.
8. Form 23's completion and legacy `all_exit_tasks_completed` automation can no longer bypass the timed HR-controlled completion path. Generic lifecycle-change routes cannot override an initiated offboarding workflow.
9. Document verification links an existing same-employee Document Centre record and requires HR. No file copies, unrestricted URLs, storage paths or new employee sharing rights are introduced. HR must confirm the actual required-document set; a linked verification record is not a claim that a configurable completeness rules engine exists.
10. Notifications use the existing recipient-isolated centre, generic previews, deduplicated event/recipient identifiers and permission-checked workflow links. Staff Home shows own pending onboarding items and a workflow link. My Profile and the lifecycle screen link to existing authorized modules. Existing account provisioning and mandatory password-change gates are reused unchanged.

## Files changed for Task 09

- `backend/routes/lifecycle.py` — initiation, scoped checklist listing/updates, explicit completion and scheduled-revocation authorization.
- `backend/utils/lifecycle_workflows.py` — responsibilities, safe DTOs, shared clearance templates, audit, notifications, timed revocation and archival guards.
- `backend/routes/onboarding.py` — read-only employee GET, validated statuses, due offsets, idempotent legacy-compatible templates and delegated updates.
- `backend/automation/engine.py` — shared creation, guarded exit outcomes and scheduled approved revocation.
- `backend/routes/automation_routes.py`, `backend/utils/task_access.py` — alternate task-route enforcement.
- `backend/routes/employees.py`, `backend/utils/employee_integrity.py` — prevent generic state overrides of initiated offboarding.
- `backend/utils/notification_centre.py`, `backend/utils/staff_home.py` — authorized workflow links and personal onboarding actions.
- `backend/server.py` — register lifecycle routes.
- `backend/tests/test_lifecycle_workflows.py`, `backend/tests/test_password_change_enforcement.py` — workflow, ownership, recovery, timing, document, audit, notification and first-login route regressions.
- `frontend/src/pages/Onboarding.js`, `frontend/src/pages/Onboarding.test.js` — extend existing tracker and test its employee/HR states and controls.
- `frontend/src/services/api.js`, `frontend/src/components/Sidebar.js`, `frontend/src/pages/EmployeeProfile.js` — API/navigation integrations.
- `docs/task09-onboarding-offboarding-report.md` — this report.

Other uncommitted Task 07/08 files are intentionally preserved; the list above identifies Task 09 edits, not every working-tree difference from HEAD.

## Verification

Final verification after the independent timed-revocation correction:

| Check | Result |
| --- | --- |
| Complete backend `pytest backend/tests tests` | **866 passed**, 6 warnings, 139.17 seconds |
| Focused lifecycle regression suite | **29 passed** |
| Complete frontend suite | **116 passed**, 20 suites |
| Strict build (`CI=true`) | Passed; compiled successfully |
| Normal production build (`CI=false`) | Passed; compiled successfully |
| Python `compileall -q backend` | Passed |
| `git diff --check` | Passed (only Git's informational LF/CRLF conversion notices) |

Tests used in-memory synthetic fixtures and an explicitly guarded disposable MongoDB/API on `127.0.0.1:27089`/`:18089`. Outbound application traffic was blocked. No production or staging connection was used. The existing disposable test harness supplies a synthetic antivirus verdict; actual file-validation tests and production fail-closed scanner behavior remain covered by Task 08 regressions.

Coverage includes explicit/read-only initiation, canonical and legacy references, repeated and partial workflow creation, role/employee isolation, HR-only offboarding, self-approval rejection, completed-item immutability, future cutoff rejection, account ambiguity, active-report archival guards, session invalidation, audit evidence, private document ownership, notification deduplication, scheduled authorization, unapproved/non-HR authorizers, unfinished-clearance access revocation, and mandatory-password-change gating of every new route. Existing Tasks 01?08 regressions passed in the complete suites.

Cleanup verified: the three disposable localhost suite databases were removed; the synthetic API and MongoDB processes were stopped; `.mongo-test`, `.test-deps` and `.node-test` were removed; ports 18089 and 27089 are no longer listening.

## Remaining HR decisions and staging prerequisites

- HR must verify each actual employee link, saved manager, eligible responsible accounts, contract notice, final day and exit authorization. This task did not reconcile or alter the live roster. Legacy exited records/accounts are not silently repaired.
- HR must approve mandatory documents by worker type and verify them in the Document Centre. Existing private sharing and antivirus/storage prerequisites from Task 08 remain. Uploads still fail closed without the approved scanner.
- Required documents, statutory/payroll registrations, asset returns, external application revocation and outstanding obligations are recorded as responsible-party attestations. There is no existing integrated asset inventory, external-account revocation connector or payroll reconciliation source to validate these automatically. Solvit login revocation is implemented; external systems still require IT action.
- Existing FORM-31, FORM-23 and FORM-24 remain available. Automated contract-derived notice calculation, final-dues pack, certificate generation and calendar exit-interview booking are not completed by this focused lifecycle extension; use the existing forms/document process and approved HR procedures pending those integrations.
- Existing welcome email/reminder infrastructure is retained; delivery, pre-arrival timing, provider credentials and templates need staging verification. No new email/SMS channel or real notification delivery was exercised.
- Verify scheduler operation, clock/timezone, worker topology and monitoring in staging. Revocation runs on the first eligible scheduler tick, normally within 60 seconds after 17:00, and after restart if overdue. It cannot run while the application is down. HR pre-authorization is required; an ordinary checklist completion cannot schedule account shutdown.
- Missing/ambiguous login links or revoked HR authorization block automatic action and require operator review. Shared integrity-lock conflicts may delay processing; monitor overdue approvals and audit evidence. No stale-lock expiry or unsafe automatic removal was added.
- Multi-document updates are not a MongoDB transaction. Unexpected interrupted writes retain the existing persistent lock. Before controlled recovery, quiesce writers and inspect the authorization audit, account active state, session invalidations, `offboarding_access_revoked_at`, checklist state and archival marker. Follow `docs/employee-integrity-rollout.md`; never delete a live writer's lock or blindly replay account changes.
- No migration is required for additive application fields; no index was installed. Existing Task 02 staging/index prerequisites remain; direct database writers bypass application-level safeguards.
- Ready for isolated staging validation once the checks below pass, not approval to deploy or approval of HR policy. Production rollout requires the above operational and policy confirmations.
