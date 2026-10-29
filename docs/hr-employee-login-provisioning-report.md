# Limited HR employee login provisioning — 29 October 2026

The user approved this limited HR permission expansion on 29 October 2026. Review the exact employee accounts before granting access; credential entry and creation submission remain operator handoff steps.

## Proposed scope

- Reuse the existing employee-account and login-review endpoints for HR Admin as well as IT Admin. HR Manager and ordinary staff remain denied.
- Add an Employee logins panel to the existing Employee Database for HR Admin, reusing the account form and readiness review. Roles & Permissions, role assignment and permission-matrix administration remain IT-only.
- New accounts receive only the Employee role and `must_change_password=true`. Existing server-side password-change gating remains unchanged: login/refresh cannot unlock protected modules before password change completion.
- HR may link an existing ordinary Employee account, preserving its password, role and activation state. Existing manager, HR, Finance, executive, Board, IT and custom-role accounts require IT administration. No existing passwords are reset.
- Preserve tenant boundaries, unique identity checks, eligibility checks, audit history, Board-only visibility and the persistent integrity lock. HR review responses omit internal account IDs. Switching account or role clears previously displayed review data.
- Initial passwords remain password-form inputs protected by the existing minimum-length/common-password policy. No default password, real credentials or invitations are hardcoded, logged or added to this report. This change does not introduce Microsoft integration or automatic email delivery.

## Rollout

1. Approve enabling this limited HR Admin account-creation capability.
2. Release tested code through the existing deployment process.
3. Review the current FTE account links in an authenticated HR Admin session. Do not assume all 21 need new accounts.
4. Confirm the exact missing/linkable accounts before granting access. The operator enters initial credentials and submits credential-creation forms; credentials are not pasted into chat.
5. Review results, leave existing privileged/ambiguous accounts for IT, and verify mandatory password change before employee access.

## Validation

- Full backend: 1,221 passed, 321 existing integration/environment skips, five existing warnings.
- Full frontend: 229 passed across 31 suites.
- Strict production build, Python compilation and whitespace checks passed.
- Backend verification covers limited role access, new Employee-only accounts, mandatory password change, privileged-account protection, idempotent linking, password preservation and HR Board visibility. Existing first-login, refresh-token, employee-isolation and module regressions are included in the full suite.
- No production accounts or configuration were changed while preparing this proposal.
