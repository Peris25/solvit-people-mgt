# HR employee leave balances — 4 November 2026

HR Admin, HR Manager and General Manager can open Leave → Employee Balances.
The server also checks the current M18 permission and each employee identity.
Other roles cannot use the overview API. Existing personal and manager APIs are unchanged.

This read-only view reuses `utils.leave_balances.balances`; no snapshots, accrual
rules, requests or approvals are modified. It shows saved FTE records, including
their recorded status, with name search, department filter and 20-row pages.
Balances are calculated only for the page requested, with at most four in flight.
The roster is tenant-scoped; Solver records are excluded. No roster is hardcoded.

Annual accrued, used, remaining and available-to-request values are shown as
returned by the existing calculator. Other leave-type remaining balances are
shown separately. Positive current-year annual pending units are listed separately;
zero pending labels are omitted. Unknown values are never converted to zero.
Legacy derived estimates, snapshot conflicts, ambiguous identities and missing
availability are marked for HR review. Existing calculator warnings are available
under Balance source. This screen does not reconcile discrepancies automatically.

Validation: 1,370 backend tests passed, 321 skipped (environment-dependent tests),
283 frontend tests passed in 39 suites; strict and normal builds passed;
Python compilation and whitespace checks passed. Production account acceptance
and balances must be checked after Render finishes the release. No production
database or existing leave records were accessed or changed during development.
