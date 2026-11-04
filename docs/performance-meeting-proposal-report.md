# Portal review meeting proposals

Implemented 4 November 2026.

## Flow

1. Employee submits self-assessment; reporting manager completes their assessment.
2. The reporting manager selects a proposed date/time using the portal date picker or suggested dates and clicks Propose review meeting.
3. HR and the employee receive linked notifications. The review shows Awaiting HR confirmation; a proposal is not a confirmed calendar booking.
4. HR arranges the meeting manually, accepts or adjusts the proposed date/time, enters the location and clicks Meeting set.
5. Employee and manager receive confirmation notifications, also available through the existing dashboard notifications. The existing portal calendar displays the confirmed meeting.

No Outlook integration, external calendar booking or new email delivery was introduced. Existing HR scheduling remains available for reviews without a proposal. Scores, assessment permissions and historical records are unchanged.

## Security and compatibility

- Only the current direct reporting manager with performance write access can propose a date, after manager submission and before a meeting is confirmed.
- Employee self-proposals, unrelated managers, forged fields, past/invalid/timezone-free dates and proposals after confirmation are rejected server-side.
- HR alone confirms meetings. Existing self-review restrictions remain.
- Proposal changes use the shared integrity lock and existing audit/deduplicated notification mechanisms.
- Employee and manager receive only their authorized review links. Proposal notifications stop displaying after HR confirms the meeting.
- Date suggestions use existing recorded working days, holidays, approved leave and portal meetings; availability must be confirmed manually.
- No migration required; no live reviews, employee records or meetings were changed during development.

## Files

`backend/routes/performance.py`, `backend/utils/performance_workflows.py`, `backend/utils/notification_centre.py`, `backend/tests/test_performance_workflows.py`, `frontend/src/components/PerformanceWorkflow.js`, `frontend/src/pages/Performance.test.js`, `frontend/src/services/api.js`, and this report.

## Checks

- Full backend: 1,438 passed, 321 skipped, five existing warnings. Additional notification-preview regression passed in the focused suite (68 passed, one skipped).
- Full frontend: 313 passed across 43 suites.
- Strict CI build and normal production build: passed.
- Python compilation and whitespace checks: passed.
- Live authenticated HR/manager acceptance remains necessary; no actual performance decisions or meetings were submitted in production tests.
