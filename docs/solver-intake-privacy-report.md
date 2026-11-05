# Solver intake privacy restriction

Requested access: Solver Requisitions, Eligible Solvers and Ineligible Solvers are available only to HR Admin and IT Admin.

## Implementation

- Central server policy explicitly permits `hr_admin` and `it_admin`; module overrides and manager roles cannot bypass it.
- Applied to private requisition reads/writes, QR generation, applicant lists/details/updates, CV downloads and CSV exports. Authorization runs before applicant update lock acquisition and remains enforced in the service.
- General Recruitment queries exclude Solver candidates for other roles using an AND scope that request filters cannot overwrite. Direct record access inherits that scope; Solver candidate creation also requires the explicit intake policy.
- Applicant-specific internal alerts target authorized administrators rather than Solvers Managers.
- Navigation hides these sections from other roles; direct page routes refuse to mount private pages. IT receives narrow intake navigation without a broad operational Solver or Recruitment module grant.
- Existing tenant isolation, private file checks, audit trails and HR-only activation confirmation remain intact.
- Public applications, operational Solver directory and separate assessment questionnaire/reviewer permissions are unchanged. No employee, applicant, Solver or account records were modified.

## Changed files

- backend/routes/recruitment.py
- backend/routes/solver_intake.py
- backend/utils/legacy_security.py
- backend/utils/solver_candidates.py
- backend/utils/solver_intake_access.py
- backend/tests/test_administrative_reporting.py
- backend/tests/test_solver_candidates.py
- backend/tests/test_solver_intake_privacy.py
- frontend/src/App.js
- frontend/src/components/Sidebar.js
- frontend/src/components/SolverIntakeAccess.js
- frontend/src/components/SolverIntakeAccess.test.js
- docs/solver-intake-privacy-report.md

## Validation

Frontend: 342 tests passed across 48 suites. Strict CI and normal production builds passed. Python compilation and whitespace checks passed.
Backend: 1,532 passed, 321 skipped, five existing deprecation warnings. Tests use synthetic local configuration, with background jobs and outbound emails disabled; no production database is accessed.

## Deployment

Push to main invokes existing cPanel frontend and Render backend auto-deployment. Both releases must finish before the access restriction is effective everywhere; a successful push alone is not live verification. No migration or index installation is needed. Existing emails already delivered cannot be recalled.
