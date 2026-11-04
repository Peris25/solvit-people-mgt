# Eligible Solver applicant editing

Implemented 4 November 2026.

## Completed

- Eligible Solvers now has an Edit button and an applicant edit dialog for authorized HR and Solvers Managers.
- Editable details: name, email, phone, county and town/area. Each change requires a reason and is audited.
- Supported recruitment stages: Eligible, Interviewing, Awaiting assessment, Passed, Awaiting confirmation, Active, On hold, Not selected and Withdrawn. These are supported choices, not user-configurable stage definitions.
- Legacy Stage 1 eligibility passes display as Eligible. An application's legacy `Active` status is not treated as confirmation of an Active Solver. Reads do not rewrite records.
- Only HR may confirm Active, after a saved Passed or Awaiting confirmation stage and explicit confirmation. This creates one linked Solver directory record without inventing an onboarding date, assessment score or login account.
- Confirmed applicants link to the Solver directory for subsequent Solver edits. Existing employee-linked applicants cannot be converted again.
- Tenant scope, existing role permissions, persistent integrity-write locking, duplicate contact checks, stale-edit protection and audit-before-publication are enforced server-side.
- Generic recruitment update/conversion routes cannot bypass the dedicated intake-Solver workflow. FTE recruitment remains separate.
- Unchanged saves preserve legacy values and timestamps. Assessment answers and original eligibility checks are not editable here.

## Changed files

- `backend/utils/solver_candidates.py`
- `backend/routes/solver_intake.py`
- `backend/routes/recruitment.py`
- `backend/tests/test_solver_candidates.py`
- `frontend/src/components/SolverApplicantEditor.js`
- `frontend/src/components/ApplicantDetailModal.js`
- `frontend/src/pages/EligibleSolvers.js`
- `frontend/src/pages/EligibleSolvers.test.js`
- `frontend/src/services/api.js`
- This report.

## Validation

- Full backend suite: 1,426 passed, 321 skipped, five existing deprecation warnings. The additional unchanged-save regression then passed in the focused 18-test Solver applicant suite.
- Full frontend suite: 311 passed across 43 suites.
- Strict CI and normal production builds: passed.
- Python compilation and Git whitespace checks: passed.
- Tests use synthetic records and fake collections; no live applicants were edited or activated, no messages sent and no production database connected.

## Operational notes

No migration or automatic import is required. Existing list/export bounds remain 500/5,000 records. Application-level uniqueness uses the existing shared write lock; direct external database writers remain outside that protection. Interrupted multi-document writes follow the existing controlled integrity-lock recovery procedure; do not remove locks automatically. Live HR activation decisions and visual acceptance remain separate from automated tests.
