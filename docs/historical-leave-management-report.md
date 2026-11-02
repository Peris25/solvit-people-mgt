# Historical leave transcription and HR corrections

Prepared 31 October 2026. Source workbook and prepared import are private, ignored local artifacts and must not be committed.

## Behaviour

- HR Admin and HR Manager may preview/import historical source records and correct imported records under Leave > Historical records. Employee and manager access continues through existing scoped leave views.
- Imports require exact, unique work-email matches resolved to canonical employee identities. No employee/account/manager records are created or modified.
- Every supplied source day is retained, including half-days. Annual, sick and paternity records remain separate. Source approvals are preserved: Approved, Pending or Recorded when unspecified. Historical edits record a reason, revision, before/after values and actor in restricted audit logs.
- Preview before import, deterministic Mongo identities, serialized integrity writes, overlap checks and revision checks prevent silent duplication or concurrent overwrites. Reimport skips existing records, preserving subsequent HR corrections. Partial/interrupted imports require a fresh preview, which skips completed rows.
- Audit intent precedes every write; an unavailable audit store prevents the write. An intent alone is not proof of a completed write. Unexpected failures retain the existing fail-closed integrity lock and require its documented operator recovery.
- Historical entries do not generate notifications, emails or live approval automation. Employees/managers cannot amend them through approval, cancellation or supplementary-info endpoints. Live requests keep the existing two-stage workflow.
- Existing balance snapshots are never overwritten. If a current-year snapshot and imported history coexist, annual availability requires an approved reconciliation; the stored figure remains visible. Without a snapshot, existing derived estimates count Approved entries; Recorded/Pending entries remain visible without fabricating approval or deductions. Historical day totals do not establish an approved balance.

## Scope and source decisions

The first prepared import covers Valuation only: 33 entries across six current FTEs, comprising 62.5 annual, 6 sick and 8 paternity days. Another Valuation employee has no recorded source leave. Twenty-five entries are Approved, one Pending and seven Recorded. Former employees and their leave are explicitly excluded at the user's request. No employment dates are changed. Source date text lacking an explicit year uses the named 2026 sheet; original workbook remains unchanged.

The workbook's omitted October summands are retained as individual entries, not silently omitted to reproduce stale totals. HR can correct their approval status and days in the historical editor. Year-end entitlement and accrued-to-date balances remain distinct and are not imported as interchangeable balances.

## Changed files

- `backend/routes/leave.py`: typed authenticated preview/import/correction endpoints.
- `backend/utils/leave_history.py`: HR authorization, source matching, validation, identity, audit and revision guards.
- `backend/utils/leave_workflow.py`: scoped historical display and isolation from live transitions.
- `backend/utils/leave_balances.py`: preserve saved snapshots and flag reconciliation requirements.
- `backend/tests/test_leave_history.py`: synthetic authorization, identity, source duplication, overlaps, corrections, audit failure, balance preservation and validation tests.
- `backend/tests/test_leave_management.py`: freeze event timestamps alongside its existing frozen policy date, fixing calendar-dependent test failures.
- `frontend/src/components/LeaveHistory.js` and `.test.js`: import preview, correction form, status and error states.
- `frontend/src/pages/Leave.js`: HR historical tab; no supporting-info shortcut on historical rows.
- `frontend/src/services/api.js`: historical API calls.

## Validation

- Complete backend: 1,266 passed, 321 pre-existing environment/integration skips, five existing deprecation warnings.
- Complete frontend: 247 passed across 34 suites.
- Strict CI build passed; normal production build, final compilation and whitespace results verified before release.
- No production database or SMTP credentials used in tests. Background jobs and outbound email disabled.

## Operational prerequisites

Publish the matching frontend and backend before importing. Import through authenticated HR UI only; verify exact employee matches and source totals in preview. Preserve source documents outside Git. No database migration or new production index is required; deterministic `_id` provides import identity uniqueness.

Do not claim data import complete until the production UI confirms it and the resulting records are reloaded. Existing snapshots, if present, require explicit HR balance reconciliation before annual requests resume; this release does not supply a blanket snapshot overwrite action. No other departments are imported automatically.

## Remaining department source batches

Prepared 45 further entries for 12 current FTEs: Account Management 28, Operations 10, IT Support 6 and Human Resources 1. Leadership has no source leave entries; no zero-day/artificial records are created. Source bookings extending into early November of the current year are accepted without fabricating a live approval workflow. Source units including 1.75 days are preserved and editable. Future calendar years remain disallowed through this source-transcription route. No employee employment dates or saved balance snapshots are changed.

Follow-up validation: 59 targeted backend tests passed, one existing integration skip; all 247 frontend tests passed; strict CI build passed. Production data completion is verified in the authenticated HR view after each batch.

## Visible historical Edit correction

The original action was a real button but inherited reset styling; its correction form rendered beneath the long history table, making clicks appear ineffective. The action now has an explicit bordered button and opens a centered native modal dialog through a React portal. Native modal focus containment, Escape/Cancel handling, focus restoration and scroll locking keep the editor immediately reachable. Validation and server errors remain in the dialog; save/revision/authorization semantics are unchanged. Controls are disabled while saving, and no additional dependencies were introduced.

Validation: all 248 frontend tests across 34 suites passed, including dialog opening, cancellation without writes, confirmed save and server-error retention. Strict CI and normal production builds passed; whitespace check passed. The backend and stored leave records are unchanged by this UI release.

## Employee grouping, simplified statuses and HR override

Implemented 2 November 2026 following the user's explicit approval-policy change:

- My applications, Team leave and Historical records are grouped into expandable employee sections, then Annual, Sick, Compassionate, Maternity, Paternity and Unpaid categories. Each category shows approved and pending day totals and preserves individual dated rows, fractional days and historical Edit actions. Canonical employee IDs keep people with identical names separate.
- The leave UI uses Pending, Approved and Denied. Existing manager/HR routing stages remain internal and map to Pending; Rejected/legacy Cancelled map to Denied. Internal cancellation and historical audit events remain preserved rather than rewritten. Historical status editing offers only the three requested choices; Denied is stored as the compatible Rejected value.
- HR Admin/HR Manager may explicitly approve another employee's live pending request directly, bypassing manager routing. The backend requires an override reason, module authorization, policy/balance/calendar review, applicable handover and document checks. Self-approval remains forbidden. The override flag, actor, reason and timestamp are retained in approval history; audit records flag the override. The normal manager-to-HR workflow remains available. No manager identity or decision is fabricated.
- An HR-only source confirmation action accepts explicit historical IDs and revisions, preflights all selected entries, serializes writes and records audit intent before changing Recorded to Approved. It does not touch live applications, pending historical entries, dates, days, employee records or saved balance snapshots. Retries skip entries already approved. Conflicts require refresh; audit failures prevent the affected write. As with the existing import, unexpected interruption may leave partial progress and a persistent integrity lock requiring controlled operator recovery.
- The notification dropdown is anchored to the sidebar's left edge with a viewport-limited width, correcting the off-screen clipping.

### Files in this follow-up

Backend: `routes/leave.py`, `utils/leave_history.py`, `utils/leave_workflow.py`, `tests/test_leave_history.py`, `tests/test_leave_management.py`.

Frontend: `components/EmployeeLeaveGroups.js` and its tests, `utils/leaveDisplay.js`, `components/LeaveHistory.js` and its tests, `pages/Leave.js` and its tests, `components/Sidebar.js`, `components/EmployeeWorkspace.test.js`, `services/api.js`.

### Validation and live-data boundary

Complete backend: 1,274 passed, 321 existing environment/integration skips, five existing deprecation warnings. Tests use synthetic fixtures with outbound email and background jobs disabled. Complete frontend: 252 passed across 35 suites. Strict CI and normal production builds passed. Modified Python files compile successfully; whitespace and secret-pattern checks passed. No confidential workbook/import artifacts are staged.

The preceding authenticated production verification found 78 imported entries: 30 Approved, one Pending and 47 Recorded. The requested source confirmation would produce 77 Approved and one Pending, retaining all day totals. This follow-up has **not yet changed those live statuses**. The deployment browser host is unavailable, and the native fallback failed to start; frontend publication and authenticated source confirmation remain blocked by that connection. No direct production database access is used as a substitute. Saved balance snapshots still require their separate approved reconciliation where flagged.

### Subsequent deployment and source confirmation

Release 693cad9 was extracted into the production cPanel people directory on 2 November 2026; the public `main.edda326f.js` matched the tested build byte for byte. The authenticated HR source-confirmation action was submitted for 47 Recorded entries, completed, and refreshed views showed Approved totals. Browser control was stopped before the final whole-list count verification, so the expected 77 Approved / one Pending total was not independently verified in that session.

## Accruing balances and relevant HR notifications

The group summaries now show **Days taken** for approved entries in the current year and **Days remaining** from the existing employee-authorized balance API. The zero-pending totals were removed; pending status remains on the individual dated records. Balances load only when an employee section is expanded and refresh on re-expansion or record reload. Annual remaining is the server's accrued balance less approved usage; the separate available-to-request card continues to reserve pending commitments. Missing/ambiguous balances show Unavailable or Needs HR review, with retry support. No snapshot is overwritten, no opening balance is invented, and no new accrual calculation is introduced in React.

HR now receives new live leave submissions immediately, including those awaiting manager review. Recipient isolation and deduplication remain intact. Notification previews use the authorized request's current status: awaiting HR/manager review, approved, denied or withdrawn. They never copy stored medical notes, decision reasons or free-text notification payloads. HR's direct-review links respect module approval permissions and exclude self-approval. Previously pending notifications no longer claim action is required after approval.

The sidebar preview prioritizes actionable events and, for HR, hides generic updates without a safe destination; announcements remain visible. All authorized events remain available in the full Notification Centre, with existing unread receipts retained. Rows are keyboard-accessible buttons that open their authorized destinations. The dropdown opens beside the desktop sidebar, stays within the mobile viewport and has a Close control. Mark recent read applies to the most recent inbox page, including events retained in the full centre.

Changed files: `backend/utils/leave_workflow.py`, `backend/utils/notification_centre.py`, `backend/tests/test_leave_management.py`, `frontend/src/components/EmployeeLeaveGroups.js` and its tests, `frontend/src/components/Sidebar.js`, `frontend/src/components/EmployeeWorkspace.test.js`, and this report.

Validation: complete backend 1,276 passed, 321 existing integration/environment skips, five deprecation warnings. Final targeted leave/notification regressions: 73 passed, two existing integration skips. Complete frontend: 254 passed across 35 suites. Strict CI/production builds, Python compilation and whitespace checks verified before release. Synthetic tests confirm monthly 1.75-day growth, reduction after approved leave, snapshot preservation, private notification previews, immediate HR review and removal of stale approval actions. Staging/production balance reconciliation requirements remain unchanged.
