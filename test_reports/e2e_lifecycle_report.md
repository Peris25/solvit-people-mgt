# End-to-End Employee Lifecycle Test Report

**Date executed:** 2026-05-15T11:10:42.370548+00:00
**Test employee:** Alex Kamau (Test) · test.alex.kamau@solvit.co.ke
**Test candidate:** Alex Kamau (Candidate) · test.candidate.kamau@solvit.co.ke
**Total checklist items:** 42

## Summary

| Result   | Count |
|----------|-------|
| ✅ PASS    | 42 |
| ⚠️  PARTIAL | 0 |
| ❌ FAIL    | 0 |
| ⏭️  SKIP    | 0 |

**Overall result: PASS**

## Results Table

| Phase | Item | Status | Notes |
|-------|------|--------|-------|
| Phase 1 - Recruitment | 1.1 Candidate created (Application Received) | PASS | candidate_id=89d26d29-829d-47e0-b9dd-9c158d96440f |
| Phase 1 - Recruitment | 1.1 RECR-01 email recorded in Notification Log | PASS | emails_to_candidate=1 |
| Phase 1 - Recruitment | 1.2 Move to Stage 1 - Competency Test | PASS | 200  |
| Phase 1 - Recruitment | 1.3 Move to Stage 2 - Values Assessment | PASS | 200  |
| Phase 1 - Recruitment | 1.4 Move to Stage 3 - Growth Mindset | PASS | 200  |
| Phase 1 - Recruitment | 1.5 Move to Stage 4 - Physical Interview | PASS | 200  |
| Phase 1 - Recruitment | 1.6/1.7 Offer extended & accepted (outcome=Hired) | PASS | stage transitions complete |
| Phase 1 - Recruitment | 1.x Stage transitions tracked | PASS | PUT after Hired -> 200 |
| Phase 2 - Onboarding | 2.1 Employee record created (status=Onboarding) | PASS | emp_id=a38e8444-3708-43e6-b325-3052c3c5a49f |
| Phase 2 - Onboarding | 2.1 Welcome email (ONBOARD-01 family) recorded | PASS | sent=1 |
| Phase 2 - Onboarding | 2.2 REM-ONBOARD-01 (pre-arrival) fires for test employee | PASS | evaluated=1 fired=1 test_emp_fired=1 |
| Phase 2 - Onboarding | 2.3 REM-ONBOARD-02 (30-day) fires for test employee | PASS | evaluated=1 fired=1 test_emp_fired=1 |
| Phase 2 - Onboarding | 2.5 REM-ONBOARD-03 (60-day) fires for test employee | PASS | evaluated=1 fired=1 test_emp_fired=1 |
| Phase 2 - Onboarding | 2.7 REM-ONBOARD-04 (90-day) fires for test employee | PASS | evaluated=1 fired=1 test_emp_fired=1 |
| Phase 2 - Onboarding | 2.4/2.6 30-day check-in submission recorded | PASS | fixture inserted |
| Phase 2 - Onboarding | 2.9 Dedup prevents re-fire when 30-day check-in already submitted | PASS | log_count before=1 after=1 |
| Phase 2 - Onboarding | 2.8 Probation outcome=Confirmed → status=Active | PASS | transitioned |
| Phase 3 - Leave | 3.1 Leave request created (status=Pending) | PASS | id=946a63c6 |
| Phase 3 - Leave | 3.1 LEAVE-01 (pending) trigger fired | PASS | queued |
| Phase 3 - Leave | 3.2 Leave approval via API | PASS | 200 {"_id":"6a06fee81b512b3125ff3ad9","id":"946a63c6-4483-4a00-81f0-fd7dca390fe9","t |
| Phase 3 - Leave | 3.3 Leave rejection path | PASS | 200 |
| Phase 3 - Leave | 3.4 REM-LEAVE-03 fires for 3-day pending leave | PASS | evaluated=2 fired=2 |
| Phase 4 - Performance | 4.1-4.4 Review record (self+manager submitted) | PASS | id=c5e93bb7 |
| Phase 4 - Performance | 4.5 PERF-review-complete email fired | PASS | queued |
| Phase 6 - Recognition | 6.1 Peer recognition trigger fired (RECOG-01 family) | PASS |  |
| Phase 6 - Recognition | 6.3 Long-service (2-year) milestone fires | PASS | fired_for_test_emp=1 |
| Phase 8 - Policy | 8.1 Policy published (POLICY-01 trigger) | PASS | id=e6b3d3e7 |
| Phase 8 - Policy | 8.2 Policy acknowledged by Alex (fixture) | PASS |  |
| Phase 9 - Stay Interview | 9.1 REM-RETAIN-01 fires at 1-year tenure milestone | PASS | fired_for_test_emp=1 |
| Phase 11 - Disciplinary | 11.1 Disciplinary case created | PASS | id=9eb279a6 |
| Phase 11 - Disciplinary | 11.1 Notice to Show Cause issued (DISC-01) | PASS | 200 |
| Phase 12 - Exit | 12.1 Lifecycle state transition to Exiting | PASS | 200 |
| Phase 12 - Exit | 12.2 REM-EXIT-02 (final-week alert) fires | PASS | fired_for_test_emp=1 |
| Phase 12 - Exit | 12.6 REM-EXIT-01 (overdue clearance) fires | PASS | fired_for_test_emp=1 |
| Phase 12 - Exit | 12.7 Lifecycle state transition to Exited | PASS |  |
| Phase 13 - RBAC | 13.x employee role-based nav scope (configured in access_matrix) | PASS | visible=['my-leave', 'my-reviews'] hidden=['budget', 'finance'] |
| Phase 13 - RBAC | 13.x line_manager role-based nav scope (configured in access_matrix) | PASS | visible=['leave-approvals', 'team-performance'] hidden=['finance'] |
| Phase 13 - RBAC | 13.x hr_admin role-based nav scope (configured in access_matrix) | PASS | visible=['employees', 'budget'] hidden=['gp-calculator'] |
| Phase 13 - RBAC | 13.x it_admin role-based nav scope (configured in access_matrix) | PASS | visible=['masters', 'reminder-rules'] hidden=[] |
| Phase 14 - Logs | 14.1 Notification Log records test scenario emails | PASS | matching_log_rows=9/50 |
| Phase 14 - Logs | 14.2 Reminder Log records all e2e rule executions | PASS | e2e_log_rows=10 |
| Phase 14 - Logs | 14.x Reminder Rules Registry shows all 40+ rules | PASS | rules=41 |

## Cleanup Summary

Records deleted (tagged `TEST SCENARIO - DELETE AFTER REVIEW`):

| Collection | Deleted |
|------------|---------|
| employees | 1 |
| candidates | 1 |
| leave_requests | 6 |
| performance_reviews | 2 |
| policies | 1 |
| policy_acknowledgements | 1 |
| disciplinary_cases | 1 |
| disciplinary_notices | 0 |
| recognitions | 2 |
| tasks | 1 |
| onboarding_checkins | 2 |
| email_log | 9 |
| reminder_log | 10 |
| reminder_runs | 10 |

---

> This report was produced by `/app/backend/tests/e2e_lifecycle.py`.
> The runner executes phases through the live API + reminder engine, 
> bypasses the need for a 'Simulate Date' UI by backdating fixtures, 
> and auto-cleans every record it creates.