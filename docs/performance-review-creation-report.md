# Simplified HR review creation

The old form allowed HR to choose an arbitrary year and Mid Year/Year End combination, even when no approved cycle existed. The API correctly rejected that choice, but the UI gave no direct setup path.

HR now sets up the cycle once, then selects an employee and an existing configured cycle to create a review. With no configured cycles, Create Review opens the setup panel directly. The panel explains the one-time setup and existing team-distribution option. A duplicate employee/cycle selection offers Open existing review and disables creation. Missing/failed creation responses no longer close the form as if successful.

Existing deadlines, scoring-policy approval, backend authorization and historical-review duplicate safeguards remain intact. No production review or cycle was created while testing.

Files: `frontend/src/pages/Performance.js`, `frontend/src/components/PerformanceWorkflow.js`, `frontend/src/pages/Performance.test.js`, and this report. This release excludes unfinished leave-balance work.

Validation: 316 frontend tests passed across 43 suites, including no-cycle setup routing, configured-cycle submission and duplicate prevention. Strict CI and normal production builds passed; whitespace checks passed. This is a frontend-only change; backend authorization is unchanged. HR still needs to configure the real review cycle and approve its scoring policy before distributing reviews.
