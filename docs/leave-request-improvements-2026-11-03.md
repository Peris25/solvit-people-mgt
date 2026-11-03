# Leave request improvements — 3 November 2026

## Requested behavior and coverage

| Request | Implementation |
| --- | --- |
| HR sees pending applications without opening employee groups | Team Leave defaults to Pending for HR and uses a flat table, search, status filter and Refresh. Implemented in `04cdb71` and already deployed by the cPanel workflow. |
| HR approves or denies without waiting for manager routing | Existing server-authorized HR override for live requests requires a reason and policy checks. Imported pending entries use the audited historical correction dialog, preserving dates/days. Self-approval restrictions on live requests remain. |
| Withdrawn is not Denied | Cancelled/Canceled/Withdrawn display as Withdrawn. Final rejected decisions display as Denied; approval stages display as Pending. |
| Group history by employee and leave category | My Applications and historical browsing retain groups with dated records, days taken and API-provided days remaining. Team review stays flat. |
| Remove “0 pending days” clutter | Current group summaries contain no pending-day totals. The main availability card is labelled Days remaining. Pending reservations remain part of server-side availability checks. |
| Employee edits and resubmits pending applications | New authenticated `PUT /api/leave/{id}/resubmit` updates the same future pending request. Employee ownership, saved manager, dates, notice, documents, handover, overlaps, category policy and available annual balance are revalidated inside the existing integrity-write lock. |
| Final decisions cannot be edited by employee | Approved, denied/rejected, withdrawn, started and historical records are rejected by the resubmission flow. HR's audited historical corrections remain separate. |
| HR notifications are relevant and open the actual record | Existing recipient-scoped notification previews and `/leave?request=...&view=team` links are retained. Resubmission notifies the current manager and HR through the existing mechanism. No additional delivery system was introduced. |
| Every authorized request appears | Removed the silent 200-record API truncation; existing employee/manager/HR authorization scope is retained. Regression covers 205 authorized records. |

## Integrity and compatibility

Resubmission preserves the request identity, employee identity, prior approval history
and stored balance snapshots. Prior dates, type and day units are retained in an audit
history entry. Current working days are recalculated by the existing server policy,
including Saturday half-days and configured holidays. Manager and HR decisions are
cleared and review restarts at Pending Manager. Final approval checks are unchanged.
The supporting-information endpoint remains backward compatible and does not permit
date/type changes; the explicit resubmission endpoint provides those changes safely.

No historical records were reclassified, no employee requests were approved or denied,
and no balance reconciliation or database migration was run as part of this release.
Historical workbook entries still require HR's correction controls. The existing
withdrawal rule permits employees to withdraw their own future pending live requests;
withdrawn entries remain in history and a new request can be submitted.

## Changed files

- `backend/routes/leave.py`: resubmission route and complete authorized request list.
- `backend/utils/leave_workflow.py`: `can_edit`, checked resubmission, recalculation,
  review reset and audit preservation.
- `backend/tests/test_leave_management.py`: resubmission, final/started/historical
  locks, forged identity, cross-employee access, balance, overlap and list-limit tests.
- `frontend/src/services/api.js`: existing API client extended with resubmission.
- `frontend/src/pages/Leave.js`: editable dates/type, Edit and resubmit action,
  explanatory copy, server capability gating and Days remaining label.
- `frontend/src/pages/Leave.test.js`: editing/resubmission and finalized-record UI tests.
- This report.

## Validation

- Complete collected backend suite: **1,282 passed, 321 skipped**, five existing
  dependency/lifecycle warnings. Skips require an explicit disposable localhost API
  and/or MongoDB integration environment; production was not used for tests.
- Final focused leave/history suite, including two later added regression cases:
  **76 passed, 1 integration skip**.
- Frontend suite: **261 passed, 35 suites**.
- Strict CI build, normal production build, Python compilation and whitespace checks
  passed. The final frontend build/test is repeated by the GitHub deployment workflow.
- Tests used synthetic fixtures, disabled outbound email/background jobs and localhost
  connection settings. No production credentials or data were used in tests.

## Release verification

Release `82435a9` was pushed to `main`. The automatic frontend run succeeded:
https://github.com/Peris25/solvit-people-mgt/actions/runs/41624883719
Public bundle checks confirmed Edit and resubmit and Days remaining are present.
Render's new resubmission route changed from 404 during deployment to 401 for an
unauthenticated request, confirming that it is present and authentication is enforced.
No real employee record identifier, credentials or decision were used in that probe.

Commit/push uses the approved automatic deployment setup. GitHub's frontend workflow
must report successful tests, build, encrypted upload and public HTML/asset verification.
Render separately auto-deploys backend changes. Confirm the new protected resubmission
route is available before describing backend deployment as verified. Do not submit a
real employee request or make a real leave decision solely to test this release.

Remaining verification: an authenticated employee/HR end-to-end acceptance check using
authorized test records and the separate localhost integration suite. Large histories
may eventually benefit from explicit pagination; they are no longer silently truncated.

## Leave queue loading follow-up

- HR's request table now becomes available as soon as the request API completes,
  without waiting for employee metadata, leave types, balances or rollover. Secondary
  fields have their own loading state; changing account still clears prior data.
- The open HR Team Leave queue refreshes every 30 seconds and on window focus without
  reloading personal balances or replacing the page with a spinner. Hidden windows
  skip timed refreshes. Requests are serialized and stale responses are discarded.
- List serialization reuses an authorized employee identity within a single request,
  avoiding repeated employee lookups for imported rows. No permission or identity
  cache survives that request, so worker consistency safeguards are preserved.
- Historical records are labelled **Imported leave history**: an administrative view
  of the workbook entries, not another leave application or a second balance ledger.
- Validation: **263 frontend tests / 35 suites**, **136 focused backend tests passed,
  one localhost integration skip**; strict CI build, compilation and whitespace checks
  passed. New regressions cover delayed metadata, focus refresh, and authorization
  reuse without cross-request caching. No end-to-end latency measurement or hosting
  cold-start conclusion is claimed from these tests.

## Leave action presentation follow-up

Review, Edit and resubmit, Withdraw, historical Edit and approval/denial actions now
share a small leave-specific button component. Icons are decorative, labels remain
explicit, primary review actions have a dark fill, and withdrawal/denial actions use
a red outline. Buttons have 44-pixel minimum height, keyboard focus outlines,
disabled styling, hover states and reduced-motion support. Row actions wrap and stack
on narrow screens. Existing handlers, permissions, confirmation requirements and
record lifecycles are unchanged; no deletion button was introduced.

Validation: 263 frontend tests / 35 suites passed; strict CI build and whitespace
checks passed. Automatic deployment reruns the complete frontend suite and verifies
published HTML and JS/CSS. Backend code was unchanged in this presentation release.
