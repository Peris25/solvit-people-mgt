# FTE self-service and account readiness — 21 October 2026

## Implemented

- Completed Employee-role navigation to existing self-service modules: Staff Home, My Profile, Documents, Benefits, Leave, Reviews, Learning, Policies, Surveys, Recognition, Tasks, Staff Directory, Organogram, Onboarding, assigned Projects, Forms, Notifications and Account Security.
- Reused existing module APIs and server-side scopes. Navigation does not grant HR privileges or cross-employee access. Specialized HR, Finance, IT and manager roles are preserved; no access-matrix override is installed.
- Added an explicitly invoked, IT-only FTE login review under Roles & Permissions > User Assignments. It compares saved employees and accounts, reuses canonical/legacy authentication identity resolution, and reports missing, disabled or conflicting accounts, duplicate employee identifiers/emails, and employment status/type requiring review.
- The report is read-only and returns no passwords, hashes, tokens, bank details or other confidential profile fields. Solver/non-FTE records and other tenants are excluded; unknown employment types are flagged rather than silently classified as FTE.
- Existing account creation/linking remains an explicit IT operation. New accounts retain the Employee default and mandatory initial password change. Existing accounts retain passwords, roles and activation status. Provisioning blocks exited/inactive or restricted board-only records until HR review.

## Validation

- Backend full suite: 1,163 passed, 321 skipped, 5 existing deprecation warnings.
- Frontend full suite: 220 passed across 31 suites.
- Strict CI production build: passed with the production API origin explicitly supplied.
- Python compilation and whitespace checks: passed.
- Normal production build: passed with the production API origin explicitly supplied.

Regression coverage includes ordinary employee navigation without privileged menus, IT-only report access, read-only behavior, legacy account links, missing/disabled/conflicting accounts, duplicate emails, tenant separation, unknown employment types, existing role/password preservation, inactive provisioning denial, safe errors and account-switch privacy. Existing first-login, employee-isolation, directory, document and workflow tests remain included.

## Rollout

1. Deploy backend and frontend from the approved release commit. If the report endpoint is not deployed yet, its UI shows a retryable error; existing self-service remains available.
2. IT opens Roles & Permissions > User Assignments > Check employee logins. “Linked” is an identity-linkage result, not proof that the user's password/MFA requirements or every module have been tested.
3. HR confirms the applicable FTE roster, employee status and manager assignments. Unknown types, board records, duplicates and conflicting links require review, never automatic repair.
4. IT creates or links only reviewed missing accounts using the existing form, retaining one account per employee. Initial credentials must be shared through an approved secure channel. Assign manager/specialist roles only with explicit authorization.
5. Each employee signs in, changes their initial password when required, and verifies their own profile and self-service. Managers separately verify their actual direct reports and approval tasks.

No production accounts were created, enabled, relinked or assigned new roles by this implementation. No employee data, production permission settings, MFA configuration, migrations or indexes were changed. Production account rollout and end-to-end role acceptance remain separate from code deployment.
