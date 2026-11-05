# Standard employee KPI template

HR can now maintain one reusable set of three to five standard KPIs in Performance, then copy it to selected empty mid-year/year-end employee reviews. Template fields are name, objective, measurement and target; HR chooses a common KPI due date when applying it. No employee targets are prefilled or invented.

## Use

1. Open Performance > Standard KPI template (HR).
2. Enter the standard objectives, measurements and targets, then Save KPI template.
3. Create employee reviews through the existing Create Review popup or shared cycle, if needed.
4. Choose the KPI due date, select reviews (or Select all eligible reviews), then Apply KPIs.
5. Employees acknowledge the copied goals before submitting their existing self-assessments. Existing manager assessment, HR review, meeting and scoring workflows continue unchanged.

## Protection and compatibility

- Server-side HR/general-manager authorization and existing M05 permissions apply to every operation. Existing employee, manager, tenant, Board and self-review scope restrictions remain.
- No migration or production data rewrite. The reusable template is stored as a tenant-scoped category in the existing `system_settings` collection. Reads do not create defaults.
- Template saves and bulk application use the existing persistent integrity-write lock. Version checks reject stale template saves/application. A batch contains at most 100 unique selected review IDs.
- Existing KPI sets are never overwritten or appended to. Historical, probation, submitted and acknowledged reviews are skipped with reasons. HR cannot assign their own KPIs; another authorized manager/HR must do that.
- Each review receives independent goal IDs and a copy of its template version; later template edits do not alter assigned goals. Repeat application skips previously populated reviews, so interrupted batches can be retried without duplicating KPIs.
- Existing performance audit/notification mechanisms record assignments. No new email provider, scoring policy, assessment weights, account permissions or employee records were added.
- This feature applies to existing reviews, not automatically to reviews created later. HR can apply the saved template again to new empty reviews.

## Changed files and validation

Backend: `backend/routes/performance.py`, `backend/utils/performance_kpi_templates.py`, `backend/tests/test_performance_kpi_templates.py`.

Frontend: `frontend/src/components/KpiTemplate.js`, `frontend/src/components/KpiTemplate.test.js`, `frontend/src/pages/Performance.js`, `frontend/src/services/api.js`.

Full backend suite: **1,513 passed, 321 skipped, five existing warnings**. Full frontend suite: **333 passed across 47 suites**. The new tests cover authorization, tenant isolation, validated template content, version conflicts, copy independence, idempotent application, locked/existing/own/probation/historical review preservation, partial eligibility, UI selection, unsaved edits and errors. Python compilation and whitespace checks passed. Strict CI and normal production builds passed.

HR still supplies the actual standard KPI wording and targets. None were entered into live employee reviews as part of implementation or testing. Live functional application should be verified with HR-approved targets and selected reviews.
