# Employee roster cleanup — 21 October 2026

## Live read-only reconciliation

The authenticated Employee Database showed 27 non-Exited records and one Exited record, with search and department filters cleared. Against the 21-person Team Directory, 19 people matched (including shortened names and business-email aliases). Two reference people were not in the visible list. Nine records fell outside the reference roster: eight matched the extended demo seed definitions, and one was a non-reference record not proven to be a demo. The user confirmed removal of the exact nine names in the conversation. Personal roster details are kept out of this repository report.

These are application-visible counts, not an unrestricted database census. No production database connection was used. Do not confuse the separate Solver population with FTE records.

## Implementation

- Removed demo generation, its handler and its API client method from the Employee Database in every frontend environment.
- Added an HR Admin removal action and authenticated, tenant-scoped DELETE endpoint requiring the exact current employee name.
- Blocked removal of the caller's record, protected Board records, employees with login accounts (including normalized-email fallback links), and employees with any direct reports, including historical/Exited reports.
- Serialized removal through the existing persistent integrity lock. Before removal, save a restricted full recovery copy in `removed_employee_records` and a minimal audit event. No public recovery-copy endpoint is provided. Accounts, documents, leave and other history are not deleted or rewritten. A removed employee's profile is no longer available through the active employee API; recovery requires a controlled operator review.
- Backup/audit failures prevent removal. Unexpected write failures retain the integrity lock for the existing controlled operator recovery procedure; no timeout-based lock clearing was added.
- No roster was hardcoded into application logic. No employee was automatically created, reclassified, assigned a manager or given an invented start date.
- Added an explicit HR "Existing employee" registration option: unknown start dates and role levels can remain unrecorded, no probation end is invented, and new-hire automation/welcome delivery is skipped. Ordinary new-hire creation still requires a valid start date. Existing login accounts are not created or changed as a side effect. Removal confirmation now uses an in-page dialog with error feedback rather than a native browser popup.

## Validation

- Backend: 1,182 passed, 321 skipped (existing integration/environment skips); five existing dependency/lifecycle warnings.
- Frontend: 224 passed in 31 suites; strict production build passed.
- Fifteen new backend tests cover authorization, tenant isolation, name confirmation, canonical/storage account links, normalized-email links, reporting dependencies, self/protected records, retained history/recovery copies, backup failure, unknown dates and existing/new-hire notification behavior.
- Frontend regression covers absence of demo generation even in development and confirmation before removal.
- Python compilation and whitespace checks passed.

## Release and data work

The backend must be deployed before the new Remove action can work. The nine confirmed production removals have not yet been executed. Expected reference count after all nine removals: 19 visible matching employees; reaching 21 requires resolving/adding the two absent reference entries without invented employment facts. Linked-account/reporting safeguards may block individual removals and require explicit review rather than automatic account deletion or manager reassignment.
