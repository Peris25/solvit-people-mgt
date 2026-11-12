# Performance V3 implementation status

12 November 2026. Work in progress, not a completion or deployment report.

## Existing functionality preserved

The previously committed HR role KPI library remains unchanged. Its draft saving,
editable role KPIs and approval-reference publication requirement remain available.
No existing employee, review, score or production record was changed in this work.

## Local foundations implemented

- `backend/utils/performance_v3_scoring.py`: fixed 50/30/20 calculations, numeric,
  binary and rated KPIs, approved group weights, five peer dimensions, minimum
  three responses, company NPS/CSAT and two-decimal rounding.
- `backend/utils/performance_v3.py`: draft service foundations for individual KPI
  assignment, four-week cycle preparation/opening, privacy projections and evidence
  checks. The approved KPI account-setup hook, own-KPI read endpoint and V3
  privacy projection are integrated. Cycle-opening and assignment mutation
  services remain unregistered until the wider workflow is complete.
- `backend/utils/performance_v3_reviews.py`: validated self-assessment and manager
  assessment transitions, stale-version checks, changed-actual explanations and
  HR compilation gates. Callers must use the existing integrity write lock.
- `backend/utils/performance_v3_peers.py`: scoped reviewer tasks, anonymous response
  storage, atomic submission claim and duplicate protection. No individual response
  endpoint is exposed. A `Submitting` claim is never automatically removed after
  an uncertain write; controlled operator recovery remains to be documented.

The full V3 assessment workflow is not routed into the running portal while its
meeting/release stages remain unfinished. Compilation does not establish readiness.

## Approved decisions implemented

- HR and the assigned current line manager can see anonymous peer aggregates
  after collection closes and at least three responses exist. Employees see them
  only after HR release. Retention answers remain HR-only. Unknown response
  metadata is excluded from the projection.
- Account creation/linking assigns an exact, unambiguous, approved role KPI set
  immediately, without overwriting existing assignments. Missing, incomplete or
  ambiguous approved roles are left for HR; no targets are invented.
- Employees can read their own assigned KPIs under Performance, including through
  legacy employee identity resolution. The endpoint accepts no employee selector.
- New onboarding checklists contain a line-manager Week 3 KPI check (day 14).
  Existing checklists and accounts are not bulk changed.
- Frontend files: `frontend/src/components/MyRoleKpis.js`, its tests,
  `frontend/src/pages/Performance.js`, and `frontend/src/services/api.js`.
- Existing backend integrations changed: `backend/utils/employee_accounts.py`,
  `backend/utils/performance_workflows.py`, `backend/routes/performance.py`, and
  `backend/routes/onboarding.py`.

## Validation executed

- New calculation, assessment authorization and peer isolation tests: **46 passed**.
- Final full backend suite after integration and privacy regressions: **1,679
  passed, 321 skipped**, five existing warnings.
- Python compilation passed for the new service modules.
- Python compilation and tracked diff whitespace check passed. Staged-diff and
  secret-pattern checks are required before committing.
- Full frontend suite: **358 passed in 51 suites**.
- Strict CI and normal production builds passed.

## Required before release

1. Complete and test meeting proposal, HR scheduling/completion, score release,
   acknowledgement/dispute and probation transitions.
2. Complete peer nomination/extension controls and interrupted-write recovery.
3. Integrate the existing Alignment Survey without exposing individual responses;
   implement the approved aggregate reporting and outcome/compensation handoffs.
4. Register authenticated routes using the existing integrity lock and permission
   checks; prevent alternate legacy routes from mutating V3 records.
5. Build the HR and employee screens, document selectors and Staff Home actions.
6. Add authorized notification deep links and reminders. Pending draft notice
   helpers must not be used until peer/Alignment links are implemented correctly.
7. The two visibility/onboarding decisions are approved and implemented as above.
   Existing accounts without assignments still require HR mapping; no automatic
   production backfill has been performed.
8. Review all draft service paths, run full backend/frontend suites, strict and
   normal builds, compilation and whitespace checks, then commit/push and verify
   the deployment. No partial workflow should be published as complete.

HR still supplies real targets, missing weights/group blends, approval references,
review dates, reviewer nominations and verified company NPS/CSAT. The application
must not invent these inputs.
