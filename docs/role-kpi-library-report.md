# Role KPI library first implementation

## Scope

This release implements HR KPI preparation using Performance Review Logic for IT V3 and Solvit KPIs by Role.pdf. It does not claim completion of the revised V3 assessment engine, anonymous 360 process or cycle rollout. No production employee, manager, date, review or score records were imported or changed during development.

## HR workflow

Performance > Role KPI library > choose a role > expand a KPI > edit > Save draft. Changes auto-save as drafts 1.2 seconds after typing stops; wait for the confirmed saved message before leaving. Incomplete target/weight/evidence-source fields can be saved and restored after login. The browser warns before closing with unsaved changes. Explicit Save draft remains available. Auto-save is server-side persistence, not browser-only storage.

Publish approved KPIs requires an approval reference as explicitly approved by the user, complete fields, confirmed scoring directions and valid weights. Save errors retain typed input. Stale-version conflicts prevent overwrites and provide an explicitly labelled discard/reload option. Edits typed during an outstanding save are retained and are not falsely reported as saved.

HR can add roles and KPI rows, remove rows and edit role/scope, objective, measurement, descriptive and numeric targets, unit, weight, direction, data source, owner, notes and approval reference. KPI cards are expandable for a compact list. Existing HR-authorized General Manager access is preserved; no new account privileges were granted.

## Reference data and approvals

13 role profiles and 110 KPI rows are provided as read-only application reference drafts until an HR save. No lazy seeding or database migration runs on read. The reference JSON contains business KPI definitions, not the PDF, employee roster, names, contact details or start dates.

PDF-provided weights remain proposals. Missing weights stay null. Compound weekday/Saturday targets and unresolved measures are marked for confirmation. The Growth Captain recruitment scorecard and MD Board reference stay as drafts while scope/scoring is unresolved. HR can prepare approved replacements without invented targets. Annual/probation applicability remains explicit, not automatically inferred from an employee's title.

Finance and Operations preserve their separate 100% subgroups. Publication also requires a confirmed 100% split between those groups, preventing a false 200% total. Rated KPIs are represented separately from numeric and done/not-done methods. Zero numeric targets remain blocked pending an approved calculation rule.

## Security and data integrity

GET /api/performance/role-kpi-library and PUT /api/performance/role-kpi-library/{role_id} enforce existing HR permissions server-side. Unauthorized writes are rejected before acquiring the integrity lock. Reads and writes are tenant-scoped. Saves use the existing integrity lock, deterministic MongoDB IDs and optimistic versions. Audit entries retain actor, before/after, reason and approval reference. Editing a previously published role requires a reason; saving a new draft retains the prior published snapshot.

Uses the existing system_settings and audit_logs collections. No new collection, dependency, environment variable, migration or production index installation is required.

## Compatibility and next stage

The previous standard template is retained under a collapsed Previous standard template and existing reviews section, preserving existing records and workflow. Its prior APIs remain unchanged.

Publication in the new library does not assign or rewrite employee KPIs, apply weights to the legacy manual-score engine, recalculate historical scores or open a review cycle. Next work is the V3 employee-role assignment/individual overrides and locking, actual-based weighted scoring, self-review inputs, 360 anonymity/aggregation, NPS/CSAT calculation, meeting-completion release gate and cycle tracker. Published role templates are stored ready for that integration. These remaining steps must be completed before claiming V3 annual reviews are launch-ready.

## Validation

Backend: 1,618 passed, 321 skipped, five existing deprecation warnings.
Frontend: 354 passed in 50 suites.
Strict CI and normal production builds passed.
Python compilation and whitespace checks passed. Tests use synthetic local configuration, with background jobs and outbound email disabled. No live inbox or authenticated browser upload was used.

Tests cover authorization, tenant isolation, incomplete draft restoration, approval reference and exact weight requirements, two-level group weights, published change reasons, prior snapshot preservation, version conflicts, audit failure, resource limits, autosave, edit-during-save preservation, explicit conflict recovery and soft server failures.

## Files

- backend/data/role_kpi_reference.json
- backend/utils/role_kpi_library.py
- backend/routes/performance.py
- backend/tests/test_role_kpi_library.py
- frontend/src/components/RoleKpiLibrary.js
- frontend/src/components/RoleKpiLibrary.test.js
- frontend/src/components/KpiTemplate.js
- frontend/src/components/KpiTemplate.test.js
- frontend/src/services/api.js
- docs/role-kpi-library-report.md

## Deployment

Main-branch push invokes the existing frontend cPanel and backend Render auto-deployments. Both must complete before live use. A successful push is not live verification; final authenticated browser checks remain outstanding. HR must confirm proposed weights, missing targets, applicability and the source-document policy conflicts before publishing the relevant role.
