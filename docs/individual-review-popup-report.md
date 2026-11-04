# One-popup employee reviews and probation reviews

Supersedes the creation flow in `performance-review-creation-report.md`.

## HR flow

Create Review always opens one popup, even when no shared cycle exists. HR selects the employee, Mid-year/Year-end/Probation type, review start, employee submission deadline, manager submission deadline and HR completion deadline. The review year follows the start date. Creation sends the existing employee notification. No separate configuration page or global cycle is required; shared team-cycle distribution remains optional.

Annual/mid-year reviews require HR's explicit scoring-policy choice and confirmation within the popup because the source documents disagree on weights. Deadlines must be ordered and fit the documented four-week window. Existing shared cycles, historical scores and approvals are unchanged.

Probation Review adds Month 1, 2 or 3. Eligible employees are recorded as Onboarding/Probation, or Active with explicitly recorded onboarding In_Progress. The backend independently enforces eligibility and the current reporting-manager link. Probation self-assessment does not require annual KPI sign-off. Manager assessment uses the existing Form 08 qualitative delivery/values/evidence criteria. Early reviews recommend continuation; Month 3 can recommend confirmation, a one-month extension or failure. HR records its review, and releases the outcome separately. Neither a recommendation nor HR review automatically changes employment status, confirms employment or terminates an account.

The existing manager proposal, HR Meeting set confirmation, notifications, privacy and audit mechanisms are reused. No numeric annual weights or invented probation scores are applied.

## Sources

- User clarification: one employee-specific popup with every deadline, plus Probation Review for onboarding employees.
- Developer Brief v1, page 4: probation reviews at days 30/60/90, final Pass/Extend/Fail; source references FRD 5.3.
- FRD, Form 08 (page 45): monthly probation review, categorical assessments and documented recommendations.
- Existing `backend/routes/forms_data.py` Form 08: qualitative delivery, values, evidence and recommendation fields.
- Existing annual-cycle implementation retains the four-week window and explicit approval of conflicting documented annual weights.

## Files

`backend/routes/performance.py`, `backend/utils/performance_workflows.py`, `backend/utils/individual_reviews.py`, `backend/tests/test_individual_reviews.py`, `frontend/src/components/CreateReviewDialog.js`, `frontend/src/components/CreateReviewDialog.test.js`, `frontend/src/components/PerformanceWorkflow.js`, `frontend/src/pages/Performance.js`, `frontend/src/pages/Performance.test.js`, and this report.

## Validation and limits

- Full backend: 1,454 passed, 321 skipped, five existing warnings.
- Full frontend: 319 passed across 44 suites.
- Strict CI and production builds, Python compilation and whitespace checks passed.
- Covered HR-only creation, missing global cycles, date/policy validation, duplicates, probation eligibility/months, employee isolation, qualitative manager/HR workflow, meeting notifications and unchanged employment status.
- Tests used synthetic records; no real review, account, notification or employment-status decision was submitted.
- No migration required. This release excludes unfinished leave-reconciliation work.
- HR must verify actual onboarding classifications and manager assignments; this release does not rewrite them or create reviews automatically.
