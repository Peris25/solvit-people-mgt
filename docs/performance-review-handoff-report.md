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

## Confirmed dashboard, email and manual-calendar clarification

Staff Home displays a prominent assigned-review card with the employee's deadline
and a direct Open performance review action. The existing task and My Reviews
views also link to the authorized review.

Final employee submission calls the existing email delivery service once, using
the canonical saved manager's work email and the existing
`performance.self_review_submitted` template. A safe built-in message is used if
that template has not yet been saved; no template database seed is required.
Email contains an authenticated review link and deadline, never answers or
scores. Draft saves do not send email. A repeated submission cannot resend it.
Existing deployment email-disable controls, delivery logs and retry handling
remain authoritative. HR can see sent/failed/skipped status; delivery failures do
not undo a submitted assessment or remove its in-app notification.

After manager approval, HR can load up to ten suggested dates in the next thirty
days. Suggestions use the participants' configured working days, saved public
holidays, approved leave and existing portal review meetings. They are proposals,
not guaranteed availability or Outlook free/busy. HR must choose the final date,
time and location manually. Date suggestions perform no writes or bookings.
Meeting participants are resolved on the server as the employee and their saved
reporting manager, not client-supplied identities. A manually saved meeting is
projected into the existing Calendar with time in EAT and a link to the review;
no duplicate calendar document or external calendar invitation is created.
Calendar visibility remains limited by employee/M05 scope, and date suggestions
also require the HR user's leave visibility for both participants.

Validation for this clarification: 1,396 backend tests passed with 321 existing
environment-dependent skips; 302 frontend tests passed in 41 suites. Strict and
normal builds, compilation and whitespace checks are required before release.
Actual mail-service delivery and live three-role acceptance still need verification.
