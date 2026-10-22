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
- Employee forms reuse the Staff Directory's approved department configuration alongside configurable master options, retaining saved department values and respecting explicitly inactive master entries. This makes the documented Valuation and IT Support departments selectable without editing production master permissions or hardcoding another list.
- Registration exposed a pre-existing cycle in the live MD/HR reporting chain and an inconsistent IT Lead manager link. Added an explicit `reports_to_board` root for a Managing Director, editable only through existing HR employee administration. It cannot name an FTE manager simultaneously, cannot be assigned to other job titles, and cannot be set by line managers. HR can remove the erroneous MD-to-HR edge without inventing a Board employee or disabling cycle validation. Profiles label this explicit root "Board of Directors". This code does not rewrite existing relationships automatically.

## Validation

- Backend: 1,186 passed, 321 skipped (existing integration/environment skips); five existing dependency/lifecycle warnings.
- Frontend: 227 passed in 31 suites; strict production build passed.
- Fifteen new backend tests cover authorization, tenant isolation, name confirmation, canonical/storage account links, normalized-email links, reporting dependencies, self/protected records, retained history/recovery copies, backup failure, unknown dates and existing/new-hire notification behavior.
- Frontend regression covers absence of demo generation even in development and confirmation before removal.
- Structured API validation errors display only readable messages, without rendering error objects or echoing submitted private values. This fixes a pre-existing blank-page error discovered during production registration validation.
- Python compilation and whitespace checks passed.

## Release and data work

The removal release was deployed and the nine approved non-reference entries were verified absent. The Employee Database showed 19 matching non-Exited records and zero Exited records after cleanup. Existing account and history collections were not deleted or rewritten by this action. The user authorized adding the two missing reference employees, supplied one confirmed employment start date, and explicitly authorized a temporary date for the other pending HR correction. Registration is blocked until the confirmed reporting-root correction is deployed and the live cycle is corrected. The newest backend existing-employee registration support must also be live to guarantee onboarding delivery is skipped. No Board login/approval identity is invented: workflows needing a named Board approver remain dependent on an explicitly approved account/approval mapping.
