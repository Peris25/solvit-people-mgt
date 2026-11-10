# Flexible performance-review KPI counts

Raised the former five-KPI cap to 100 KPIs in standard templates, individual goal assignment, employee acknowledgement/self-submission and manager assessment validation. The minimum remains three; the upper bound is a resource safeguard. HR can add/remove template rows and assign additional employee-specific goals before employee sign-off.

Existing equal-weight KPI averaging, approved section weights, authorization, acknowledgement locks, probation workflow and historical records are unchanged. Template edits do not overwrite KPIs already copied into employee reviews; use the existing individual goal assignment for unsigned reviews. Signed/submitted assessments remain protected.

Frontend Add KPI and Assign goal controls now use a shared 100-KPI constant. Backend template validation reuses the review limit, preventing frontend/API mismatches. No data migration or live record updates were performed.

Regression coverage: template save/apply with 6, 12 and 100 KPIs, over-limit rejection, six-KPI acknowledgement and employee/manager submission with unchanged average scoring, and adding/removing the sixth UI row.

Validation: frontend 348 tests passed across 49 suites; strict CI build passed. Backend: 1,600 passed, 321 skipped, five existing deprecation warnings. Normal production build passed. Python compilation and whitespace checks passed.

Modified files: backend/utils/performance_workflows.py; backend/utils/performance_kpi_templates.py; backend/tests/test_performance_workflows.py; backend/tests/test_performance_kpi_templates.py; frontend/src/components/KpiTemplate.js; frontend/src/components/KpiTemplate.test.js; frontend/src/components/PerformanceWorkflow.js; frontend/src/components/performanceLimits.js; this report.

Push invokes existing frontend and backend auto-deployments. Both must complete before live use; push does not itself verify Render deployment or authenticated browser operation.
