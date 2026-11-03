# Management role implementation ? 3 November 2026

## Implemented

- Added a canonical General Manager role with the existing HR business-module grants, including employee administration, leave review/override, performance HR review, learning, documents and reporting. Existing Finance gates, separate Finance/IT signatures, protected Board records and self-approval restrictions remain in place.
- General Manager cannot list/manage accounts, provision employee logins, change roles/permission overrides, or administer technical email/AI/master settings. Existing IT-only API checks remain authoritative. HR Admin retains the previously approved limited employee-account setup.
- Added IT Admin's manager layer for saved direct reports: onboarding, performance, learning, project progress and leave. IT retains technical administration, without HR-wide compensation access. Manager signatures require an actual saved direct-report relationship.
- Updated navigation, role labels, Staff Home/team dashboard and business screens. No named employees are hardcoded into permissions.
- General Manager is classified as privileged by existing MFA controls; rollout configuration, first-login enforcement and session controls are unchanged. Existing IT role-assignment endpoint records audits and invalidates affected sessions.
- Explicit runtime permission revocations continue to override defaults. Default grants do not override persisted configuration.

## Live assignment boundary

No production accounts, passwords, employee records or manager links were changed. IT credentials are unavailable; the user explicitly deferred IT sign-in. Code deployment does not itself assign these roles.

An authorized IT administrator must review each existing linked account and assign the approved General Manager/Line Manager roles using Roles & Permissions. Preserve the existing IT Admin account and its employee link. HR must verify saved reporting links before team acceptance tests; department membership is not sufficient. Affected users must sign in again. No migrations or automatic account provisioning are included.

## Validation

- Full backend suite: 1,312 passed; 321 skipped. Skips are existing external-service/disposable-Mongo integration cases; no production database was used.
- Full frontend suite: 267 passed across 35 suites.
- Strict CI production build: passed.
- Normal production build: passed.
- Changed Python files: compilation passed.
- Git whitespace checks: passed.
- Added coverage for General Manager business grants, explicit revocation, privileged classification, denied account/security operations, HR leave review, self-approval protection and separate Finance/IT signatures. IT manager tests cover direct-report scope, unrelated-employee denial, explicit revocation, leave stage/override restrictions, performance projection and manager sign-off. Frontend tests cover management navigation restrictions and IT team dashboard integration.
- Solver onboarding notification expectations include the new authorized General Manager recipient, with retry/idempotence and recipient isolation regressions retained.

## Remaining verification

Production deployment status and live role assignments must be distinguished. After both services run the release and IT assigns roles, verify one direct report and one unrelated employee per manager, plus General Manager business access and denied account/technical administration. No live leave decisions should be made merely for testing.

## Approved HR delegation ? subsequent update

The user approved HR Admin assigning business roles without waiting for IT. This supersedes the original IT-only assignment boundary above.

- HR Admin can open Roles & Permissions directly on User Assignments and assign Employee, Line Manager, General Manager, HR Manager, Finance or Executive to an existing unambiguously linked full-time employee account.
- HR cannot edit its own role or protected HR Admin, IT Admin, Board, Solver, system or custom-role accounts, nor grant those protected roles. General Manager does not receive this delegation.
- Access matrix editing, custom-role administration and technical/security settings remain IT-only. Existing limited HR employee-login provisioning remains unchanged.
- Assignment validates the stored target identity server-side, uses tenant scoping and a conditional update to reject concurrent role/link changes, records an audit event and invalidates existing sessions.
- No production assignments have been performed by this code change. HR can now make the reviewed assignments in the portal after the backend/frontend release is live. Manager visibility still follows saved employee reporting links.
- Updated full validation: backend 1,329 passed / 321 skipped; frontend 269 passed across 36 suites. Strict build, normal build, Python compilation and whitespace checks pass. Integration skips remain as documented above.

HR usage: Roles & Permissions ? User Assignments ? select the person's approved role and confirm. Affected users sign in again. Review Martin for General Manager; Grace, Timothy and Brian for Line Manager; retain Peris's protected IT Admin account. Do not infer or rewrite team assignments during role changes.
