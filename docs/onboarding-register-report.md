# HR onboarding register — 4 November 2026

HR Admin, HR Manager and General Manager can view the FTE onboarding register,
filter Onboarded / New employees in progress / Not recorded, and record selected
employees' HR-confirmed status with a required explanation. Other roles cannot
read or update the register. Tenant and canonical identity checks apply to every
record; invalid batches are checked before any employee update.

The employee metadata records the status, recording time and recording account.
It does not claim that this is the historical completion date. Audit events retain
the previous status and HR's explanation. No employment state, start date, salary,
account, leave balance, document verification or checklist result is overwritten.
Existing checklist tasks remain available as read-only history after confirmation;
Staff Home no longer presents their onboarding checklist as outstanding. The HR
confirmation can explicitly be corrected back to In progress, with another audit.

Initiation excludes HR-confirmed completed onboarding. Active employees explicitly
recorded as In progress may use the existing onboarding workflow, retaining its
start-date requirement and document checks. The onboarding picker shows only this
in-progress group; offboarding selection and safeguards remain unchanged.

No employee names or roster are hardcoded. HR's live classification is a separate
authorized operation after deployment, not a startup seed or migration.

Validation: 1,382 backend tests passed, 321 environment-dependent tests skipped.
Frontend suites, strict and normal builds, Python compilation and whitespace
checks are run before release. Production acceptance includes confirming the
19 completed and two in-progress entries against HR's instruction.
