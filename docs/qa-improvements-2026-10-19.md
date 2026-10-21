# QA improvement implementation — 19 October 2026

## Scope

Local code corrections following `docs/qa-production-review-2026-10-19.md`. MFA work is explicitly excluded at the user's request. Authentication enforcement and existing MFA gates are preserved. No production account, employee/Solver record, reporting relationship, salary, leave balance, policy artifact or configuration has been changed. No migration, commit, push or deployment was performed.

## Implemented

| QA finding | Correction | Qualification |
| --- | --- | --- |
| QA-06 mobile navigation | Phone-sized layouts initialize with collapsed navigation. Expanded mobile navigation overlays content rather than consuming almost the entire screen. Main content has correct box sizing/minimum-width behavior and reduced phone padding. | No new dependency or branding change. Tablet/browser/device acceptance is still required before deployment. |
| QA-07 recruitment | API preserves visibility of authorized closed records and legacy/unclassified stages, normalizes known stage aliases only in the response, and keeps executive responses aggregate-only. UI shows every returned stage, offers and closed outcomes; labels the total correctly; hides transitions from read-only roles and closed records; shows a retryable load error. | No candidate record or stage is rewritten. Existing backend manager/tenant scope and sequential-transition validation remain authoritative. |
| QA-08 calendar | Onboarding events now respect the requested inclusive date window, like the other dated events. Date boundaries use EAT. | Historical employee start dates are unchanged. |
| QA-09 upcoming deadlines | Dates roll forward once their configured monthly day has passed, including December/year rollover. Dates use EAT. | Existing deadline days are preserved, not independently re-certified as current statutory law. |
| QA-04 calculator | Response identifies whether its health deduction uses the legacy NHIF table or the percentage fallback. The UI displays the actual basis and explicitly requires Finance review; it no longer calls a table-derived amount “SHA (2.75%).” Negative, nonnumeric and non-finite input is rejected safely. | Existing amounts, tax bands, relief and NSSF assumptions are preserved. This fixes misleading presentation, **not** the pending Finance-approved statutory-policy implementation. It remains an informational estimate, not payroll processing. |
| QA-03 policy acknowledgements | Server and UI block new acknowledgements without readable published content or an existing private file within the configured policy root. Publication metadata exposes a safe acknowledgement-availability flag, never a private path. Historical acknowledgements and existing policy records are preserved. Concurrent metadata changes are checked under the existing integrity lock. | This does not supply or approve Handbook v2, certify the scanner or prove that a user actually read a document. HR must publish the approved artifact. |
| QA-15 policy publication | New policies start as drafts. UI accepts full text or an approved file, saves the draft, uploads/scans the file and then publishes. Upload failure leaves the form open and retries reuse its saved draft ID. Drafts do not trigger publication notifications; actual publication/version transitions reuse existing automation/email mechanisms. | Server rejects attempts to publish unreadable content. Existing email deployment controls still apply. Refresh after an uncertain publication response before retrying. Cross-page/cross-request idempotency for an ambiguous initial create response is not newly guaranteed. |
| QA-16 production demo action | Demo-employee generation is absent outside development builds. | Existing server-side development/destructive-data guards remain intact. |
| QA-17 accessibility | Form and policy cards support Enter/Space, focus indication and accessible action names. Navigation expand/collapse controls have descriptive names. Policy cards and dialogs fit narrow viewports. | Not a complete WCAG or assistive-technology certification. |
| QA-11 count clarity | HR dashboard labels its existing metric “Active Solvers.” | No Solver is imported, activated or inducted automatically. |
| QA-13 scoring clarity | Performance explicitly distinguishes the aggregate talent-density component weights from an individual review's approved cycle policy. | Scoring weights and historical scores are unchanged. HR's policy approval is still needed. |

## Modified application and test files

- `backend/routes/calendar.py`
- `backend/routes/compliance.py`
- `backend/routes/policies.py`
- `backend/routes/recruitment.py`
- `backend/tests/test_legacy_security.py`
- `frontend/src/components/Layout.js`
- `frontend/src/components/Sidebar.js`
- `frontend/src/index.css`
- `frontend/src/pages/Compliance.js`
- `frontend/src/pages/Dashboard.js`
- `frontend/src/pages/Employees.js`
- `frontend/src/pages/Forms.js`
- `frontend/src/pages/Performance.js`
- `frontend/src/pages/Policies.js`
- `frontend/src/pages/Recruitment.js`
- `frontend/src/pages/QAImprovements.test.js` (new)
- `frontend/src/services/api.js`

Reports: this file and the preserved production QA review. No authentication/MFA implementation file or dependency manifest was changed.

## Validation

Tests use synthetic fixtures, with external-network protections; the production application is not a fixture-reset target. No new database or database migration is needed for these changes.

| Check | Final result |
| --- | --- |
| Backend collection | 1,118 passed, 321 skipped, 5 warnings; 82.39 seconds. After retaining the original policy-content version guard, the final affected backend suite was rerun: 71 passed, 2 integration skips, 5 warnings; 2.13 seconds. |
| Frontend collection | 207 passed, 30 suites |
| Strict CI build | Passed |
| Normal production build | Passed |
| Python compilation | Passed, including the final version-guard check |
| Whitespace | Passed, including the final version-guard check |

New backend cases cover calendar boundaries, deadline rollover, legacy-versus-percentage deduction labels, invalid inputs, unreadable/missing policy content, draft privacy/publication/notification behavior, versioned acknowledgement preservation and closed/legacy recruitment visibility with executive redaction. New frontend cases cover mobile initialization/manual toggling, unchanged password/MFA gates, recruitment bucket completeness/read-only controls/error retry, keyboard policy access, blank-policy acknowledgement denial, failed upload retry and preventing metadata-only publication.

Initial diagnostic failures caught a JSX error, an out-of-date count-label expectation and non-finite query validation producing a response-serialization error. Those were corrected; diagnostic results are not final pass evidence. Existing positive acknowledgement fixtures now include actual synthetic policy text; their version/idempotency assertions remain intact.

Private validation logs are in ignored `integrity-reports/qa-fixes-20261019/`. Backend integration tests that require a separately initialized database/test API remain skipped; production was not used to run destructive test fixtures. A fresh post-fix browser/mobile visual pass and designated-role end-to-end UAT remain outstanding; the earlier production screenshots describe the deployed pre-fix application, not this candidate.

## Pending decisions and work

1. **MFA:** intentionally deferred by the user; no enrollment, environment or session-policy change.
2. **QA-02/05/10/11:** HR must approve the actual reporting-cycle corrections, identities, department aliases and FTE/Solver reconciliation. No automatic data repair or count-forcing import.
3. **QA-03/12/14:** HR/technical owners must provide approved readable policy content, assessment content/assessors and onboarding dates/responsibilities. The application does not invent them.
4. **QA-04/13:** Finance/HR must confirm effective statutory rules and performance policy. Labels and explanatory text do not certify disputed formulas.
5. **QA-18:** organogram fit/zoom/list presentation remains a separate enhancement. Existing cycle/duplicate protection is retained.
6. Remaining broader QA: full roles, safe write-workflow UAT, skipped integration tests, scanner/storage/restore validation, exports, keyboard/modal focus, supported browser/mobile coverage and error/load testing. These are not marked complete by passing unit/component tests.

## Release considerations

Deploy backend and frontend together: policy creation now defaults to Draft, frontend explicitly publishes through the existing metadata endpoint, and acknowledgement availability is supplied by the backend. Mixed older frontend/newer backend can leave newly created policies as drafts without exposing them to staff. Existing unreadable published records remain stored but cannot accept new acknowledgements until HR supplies readable content. Historical data is not rewritten.

No new secrets, dependencies, indexes, migrations or authentication changes are required. Keep the existing production scanner, private storage, origins, email controls and background-job ownership policies in force. These fixes are not yet live.
