# Performance cycle distribution and HR meeting handoff — 4 November 2026

Extends the Task 10 implementation; existing reviews, scoring policies and
historical results remain unchanged.

## Workflow

1. HR configures the existing four-week review cycle and explicitly records the
   approved documented scoring policy. The pre-existing source weight conflict
   remains visible; no new weights, KPIs or ratings are invented.
2. HR chooses Send reviews to employees and confirms distribution. Eligible FTE
   records with resolvable, active reporting managers receive one review for the
   cycle. Existing assignments are retained on retry. Missing or ambiguous
   identities, manager links and restricted Board-process reviews are reported
   individually for HR follow-up; no employee records are changed.
3. Employees receive their own review notification and use the existing agreed
   goal acknowledgement and self-assessment workflow. Draft edits do not notify HR.
4. Submission notifies the saved reporting manager. The existing manager-only
   assessment changes the review to Manager_Submitted. The UI labels this action
   Approve and send to HR; HR score fields remain protected.
5. HR receives Arrange performance review meeting, deep-linked to the review.
   The Performance page also lists meetings awaiting arrangement. Only another
   authorized HR user can schedule/reschedule after manager approval, using a
   future timezone-aware time and location. The employee and current manager
   receive an in-app meeting notification. This creates no external calendar,
   email or video-conference invitations.
6. Existing HR assessment and separate score-release controls remain intact.
   Meeting scheduling does not calculate, publish or change scores. Obsolete
   assignment, manager-review and meeting-arrangement action alerts are hidden
   from counts as the corresponding stage advances. Stored events are retained.

## Security and validation

Cycle distribution and meeting writes use the existing integrity lock, tenant
boundaries and HR/M05 grants. Employee and manager scopes and self-approval
restrictions remain server-enforced. Meetings, transitions and distribution are
audited; notification previews contain no assessment text or scores.

Full backend: 1,392 passed, 321 environment-dependent skips. Final focused
performance/notification regressions: 94 passed, 2 skipped. Full frontend:
300 passed in 41 suites. Strict and normal production builds, compilation and
whitespace checks are performed before release. No production review cycle,
assessment, score or meeting was created during implementation.

HR must provide actual cycle dates, approved scoring policy, agreed employee KPIs
and meeting details. Live acceptance should use employee, reporting manager and
HR accounts to exercise the end-to-end handoff after backend deployment.
