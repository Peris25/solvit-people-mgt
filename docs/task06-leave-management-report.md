# Task 06 — Leave Management

Local implementation, 15 October 2026. Tasks 01–05 and the existing working-tree changes are preserved. No production connection, migration, balance reconciliation, commit, push or deployment was performed.

## Implementation and audit findings

The previous leave API accepted invalid/reversed dates as one day, used a Monday–Friday calculator, did not enforce notice, handover, evidence or overlap rules, and allowed a manager decision to finalize leave without HR. The AI approval executor could update requests outside the checked workflow. Generic Form 15 could emit a leave-approved event without creating a validated leave request. Saved balance snapshots were ignored by the balance endpoint.

The existing Leave screen and API now provide:

- Employee-scoped history, preserved balance figures, separate annual commitments, server-calculated working units, supporting information, tracking and withdrawal of future pending requests. Approved/started cancellation requires HR review; there is no automatic balance credit.
- Serialized creation and decisions using the existing integrity-write lock, canonical employee/manager resolution, overlapping-request rejection and submission-token replay protection. Invalid historical dates/units fail safely for HR reconciliation.
- Manager recommendation followed by a different, linked HR reviewer. Own-request decisions, forged identities and unrelated-manager decisions are denied. Runtime M18 restrictions still apply. Executives/board receive only team-scoped M18 access needed for actual direct-report manager duties, not general HR access.
- Written handover, covering colleague and recorded reviewer confirmation; manager sign-off must occur by the last working day before planned leave. HR must confirm contract eligibility, recorded balance and holiday calendar before final approval. Department absence conflicts are checked at final annual approval under the write lock.
- Category-specific supporting-document and duration checks, private evidence upload/download, preserved approval history and metadata-only audit entries. Medical evidence is accessible only to the employee and authorized HR; managers do not receive medical notes/documents in request lists.
- Generic, recipient-authorized Notification Centre updates and links to the checked review screen. Deterministic event keys prevent duplicate notices on retries. Extended sick absence creates a generic HR follow-up task. Existing best-effort email templates remain; no new delivery channel was introduced.
- AI approval redirects users to checked Leave Management; AI rejection uses its authorization checks. New Form 15 submission/signing is blocked with guidance to Leave Management; historical form records remain readable and the Forms UI opens Leave Management for Form 15.
- Responsive request/review forms, loading/error/empty states, persisted fractional balances and unknown-balance states. Staff Home shows available annual days separately from recorded figures.

## Requirements and policy traceability

Sources reviewed locally: `docs/reference/Solvit_Employee_Handbook_v2 (1) (1).pdf`, `Solvit_People_Platform_FRD.pdf`, and `Solvit People System — Developer Brief v1.pdf`. Page references below are PDF pages.

| Rule | Source | Implementation / limitation |
| --- | --- | --- |
| Contract-specific provisions take precedence | Handbook §4.1, p6 | Read-only approved `leave_policy_profiles` overrides; final HR confirmation mandatory. No contract records populated automatically. |
| Annual 21 working days; 1.75 per month of service | Handbook §5.1, p8 | Tested prospective accrual calculator and policy quote. Existing saved balances and legacy derived figures are preserved; no new ledger credits or accrual job. |
| Working calendar, holidays | Handbook §4.3, p6; Brief §3.2, p4 | Monday–Friday 1, Saturday 0.5, Sunday 0; excludes stored holiday dates. Approved individual calendar supported. HR must verify gazetted calendar completeness. |
| Planned leave approved in advance; emergency sick exception | Handbook §5, p8 | Enforced on submission; emergency sick may start retrospectively and still requires evidence where applicable and both reviewers. |
| Annual one-week notice; over five consecutive working days requires four weeks | Handbook §5.1(a), p8 | Seven/28 calendar days' notice; working units calculated server-side. No invented absolute five-day maximum. |
| Preferred annual window February–June; both approvals; department cover | Handbook §5.1(a), p8 | Both reviews always required; high-activity periods flagged; another approved department absence blocks final annual approval. Department matching uses normalized literal names, not invented assignments. |
| Planned written handover and manager sign-off | Handbook §5.1(b), p9 | Notes, active covering colleague, explicit sign-off and last-working-day deadline. Electronic reviewer action records acknowledgement; it is not a drawn signature. |
| Sick first 30 full pay, next 15 half pay, then unpaid | Handbook §5.2, p9 | Category-specific tier calculation and HR attention. No payroll deductions or rewriting historical pay. FRD contract-anniversary year is the default; approved contract may specify calendar year. |
| Sick certificate after three consecutive days; half-pay tier all absences; HR follow-up over seven working days | Handbook §5.2, p9 | Typed owned evidence required; HR document verification; HR follow-up task. The visit itself remains an HR action. |
| Maternity three calendar months; EDD evidence; earliest six weeks pre-EDD absent advice; four weeks' notice where practicable | Handbook §5.3, p9 | Calendar-month limit, EDD/evidence and medical-advice flag; short notice flagged for HR, not categorically rejected. |
| Paternity two calendar weeks within two months of birth; evidence | Handbook §5.4, p10 | Birth window, aggregate same-birth duration and evidence enforced. |
| Compassionate 14 working days/calendar year, immediate family; extra unpaid exception | Handbook §5.5, p10 | Family category and paid/unpaid allocation; additional unpaid days require documented HR exception. |
| Unpaid after annual exhaustion, prior manager + HR | Handbook §5.7, p10 | Recorded available annual balance must be exhausted at submission/final approval. No automatic payroll action. |
| Employee isolation, approvals, history and dashboard integration | FRD leave module; Developer Brief leave requirements | Server authorization, dual review, audit/history, scoped calendar, dashboard balances and Notification Centre integration. |

Handbook rules override conflicting FRD values (three-day compassionate leave, 12-week maternity) and unsupported carry-forward limits. Existing rollover values, including half days, remain unchanged; no default March deadline triggers forfeiture. The configured deadline remains informational.

## Balance compatibility and safe failure

Recognized saved snapshots take precedence and are displayed without writes. Multiple snapshots or unknown formats require reconciliation; undated snapshots cannot fund a new request. New workflow commitments are reserved separately. Legacy approved requests retain their original stored units. Pending legacy requests must be supplemented and re-reviewed; differing saved/current units require HR reconciliation or a replacement request, rather than silently rewriting them.

Without a saved snapshot the endpoint retains its previous derived figures, clearly labelled as estimates. These are not a newly approved balance ledger: historical generic sick/maternity/paternity figures must not be interpreted as final category-specific entitlements. New decisions use the category rules above. There is no automatic accrual, carry-forward, forfeiture, salary deduction or historical recalculation.

## Files changed for Task 06

- Backend: `routes/leave.py`, `routes/ai_actions.py`, `routes/forms.py`, `automation/engine.py`, `utils/access_matrix.py`, `utils/notification_centre.py`, `utils/staff_home.py`.
- New backend services: `utils/leave_policy.py`, `utils/leave_workflow.py`, `utils/leave_balances.py`.
- Frontend: `src/pages/Leave.js`, `src/pages/Forms.js`, `src/pages/EmployeeDashboard.js`, `src/services/api.js`, `src/utils/relatedRecordFilter.js`.
- Tests: new `backend/tests/test_leave_management.py`, new `frontend/src/pages/Leave.test.js`; updated employee-authorization/notification-centre tests and historical integration fixtures `test_iteration_3.py`, `test_iteration_8.py`, `test_iteration_12.py`, `test_iteration_16.py`, `test_iteration_18.py`; related-record filtering regression test.
- `.gitignore` excludes private leave evidence; this report. Earlier Task 03–05 files remain uncommitted and are not attributed to Task 06.

## Verification

Final verification:

| Check | Result |
| --- | --- |
| Full backend: `python -m pytest backend/tests tests -q` with disposable integration opt-in | **734 passed**, zero failures/skips, six warnings; 115.34 seconds |
| Full frontend: CRACO test, CI mode, `--watchAll=false --runInBand --detectOpenHandles` | **94 passed**, 17 suites; no open-handle warning in final run |
| Strict CI production build (`CI=true`) | Passed, compiled successfully |
| Normal production build (`CI=false`) | Passed, compiled successfully |
| `python -m compileall -q backend` | Passed |
| `git diff --check` | Passed; Git's existing LF/CRLF conversion notice is informational |

Earlier runs exposed past-date/missing-handover fixtures, a missing fake collection and intermittent 20-second localhost login timeouts. Fixtures were corrected without weakening assertions; affected modules passed a separate 68-test recheck and the subsequent complete run passed. No production endpoint was involved.

Tests cover accrual, half-day Saturdays/holidays, invalid dates, notice, handover, overlaps, real MongoDB concurrent creation, dual approvals, self/foreign access, sick tiers, evidence ownership, maternity/paternity windows, compassionate allocation, cancellation, unchanged snapshots, notification privacy/retries, AI/form bypass prevention and the leave screen. Frontend tests also cover account switching, unknown/zero balances, server-calculated fractional units, review-stage controls and failure states.

Integration services used only `127.0.0.1:27089` and `127.0.0.1:18089` with synthetic fixtures and outbound-network guards. All three disposable suite databases were removed and their absence verified. Owned API/MongoDB processes were stopped; neither test port remained listening. Temporary MongoDB, Node and Python test runtimes were removed and their absence verified. HEAD remains `7afbe1f700fc17352cce58d644419b4efbff14ce`.

## HR decisions and staging prerequisites

1. HR must approve contract eligibility, first-year/partial-month treatment, leave-year boundaries and actual individual exceptions. No employment contracts were supplied or inferred. Non-calendar annual accounting requires an approved reconciliation plan.
2. Reconcile historical snapshots/requests read-only before approving ledger adjustments. Confirm snapshot settlement dates so new commitments already included in an externally maintained snapshot are not double-counted. Future pending sick requests conservatively reserve the pay tiers; HR must check chronological allocation before payroll. No automatic migration or balance correction is provided.
3. Confirm department aliases/cover rules, gazetted holidays and any alternative schedules. Different legacy department names are not automatically treated as equivalent. Confirm whether the last-working-day handover deadline needs a specific time cutoff.
4. Confirm approved/started cancellation and emergency exceptions, compassionate supporting-evidence discretion, medical-document retention, permitted file types and malware scanning. Evidence storage must be private, persistent, backed up and access-controlled using `LEAVE_EVIDENCE_ROOT`; do not place it under a public static path.
5. Staging needs valid employee/account links and manager assignments, two distinct authorized reviewers (including another HR reviewer for HR employees), Task 02 database/index prerequisites and the existing controlled integrity-lock recovery procedure. Interrupted writes retain the existing persistent lock; no unsafe timeout-based lock removal was added.
6. Run HR UAT across staff, manager, HR, finance/executive direct-report duties, revoked permissions, exits, missing managers, mobile layouts, legacy requests and notification links. Verify staging SMTP isolation before testing delivery; existing email infrastructure may route formal templates outside Mailtrap. No production email was sent by local tests.
7. Audit/notification failure after a saved request returns an explicit saved-state error; refresh and operator review are required. There is no transactional outbox or automatic repair of historical events. Review operational recovery before production use.

No database migration is required to read existing records or exercise the local implementation. Production balance/index reconciliation and HR/staging acceptance remain separately approved work. This report does not claim production readiness or HR policy acceptance.
