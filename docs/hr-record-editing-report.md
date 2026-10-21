# HR record editing — 21 October 2026

## Approved change

The user explicitly requested direct HR record administration without external legacy-system verification. This supersedes the earlier requirement that HR use induction gates for every activation/reactivation. Other users retain their existing restrictions.

## Changes

- Solver Edit is beside the name, not hidden in the far-right Actions column. Explicit server denials remain respected; older capability responses no longer silently hide HR's editor.
- HR Admin/HR Manager can update Solver contact, region/coverage, statutory/payment, licence, onboarding date, categories/zones, recorded statistics/tier, notes and any of the five supported lifecycle states. Only changed fields are submitted, preserving unknown or unchanged historical information.
- The backend permits HR activation/reactivation and manual recorded-score corrections directly. Managers/staff/Solvers cannot use this administrative exception. The original evidence-based induction workflow remains available; no evidence, qualifications, dates or scores are manufactured automatically.
- An explicit HR status decision aligns a conflicting historical status label with the chosen current state. Actor, timestamp and previous/projected state are recorded. Activation remains unpublished if audit recording fails; HR can retry once audit storage is restored.
- Existing ratings and assessment history are not recalculated or deleted. Identity fields, account credentials and permissions are not arbitrary editable profile fields.
- HR employee-email edits now preserve an unambiguous locally resolvable account link automatically. This uses existing authentication identity rules inside the integrity-write lock. Login email/password/role/activation status remain unchanged. Actual duplicate, foreign-tenant or different-person accounts are still rejected.
- Employee start-date edits are now saved by the backend, restricted to HR rather than ordinary line managers.

## Validation

- Full backend suite: 1,167 passed, 321 skipped; 5 existing deprecation warnings.
- Full frontend suite: 222 passed across 31 suites.
- Strict CI and normal production builds: passed with the verified production API origin.
- Python compilation and whitespace checks: passed.
- Regressions cover direct HR reactivation, conflicting historical labels, manual profile/score changes, audit failure, preserved manager/staff restrictions, legacy account compatibility without password/role changes, cross-employee account rejection, visible name-column Edit controls and changed-fields-only submissions.

No live record was edited to test this release. No migration, bulk cleanup, account reset or permission override is required. Server-side uniqueness, tenant boundaries, manager-cycle checks, board privacy, account security and offboarding safeguards remain enforced.
