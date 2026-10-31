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
