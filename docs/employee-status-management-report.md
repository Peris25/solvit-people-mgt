# Employee status management — 22 October 2026

## Requested behavior

Employee rows display their current status and a single Edit action. Remove, direct lifecycle shortcuts and bulk lifecycle shortcut buttons were removed from the page. HR changes status in the existing edit form. The user confirmed all 21 current reference FTEs should be Active; the three non-Active entries were updated through the authenticated HR form, without changing their account roles, employment dates or reporting relationships.

## Implementation

- Supported employee choices: Active, Inactive, Onboarding, Probation, On Leave, PIP, Realignment, Suspended, Notice Period, Exiting and Exited. Existing internal values such as `On_Leave` are preserved. Candidate remains a legacy backend state, not a new FTE dropdown choice.
- Backend create/update/transition/bulk paths recognize the supported states consistently. Changed invalid states are rejected; unchanged historical state values remain compatible.
- Existing authorization remains unchanged: manual changes are HR Admin only, enforced server-side. The existing-record status control is disabled for HR Manager rather than presenting an action that the backend forbids. Ordinary staff and line managers cannot change status.
- Existing reporting safeguards, started-offboarding workflow restrictions, employee IDs, audit records and account permissions remain intact. Setting Inactive does not delete a record. Account deactivation still uses the existing separate account/offboarding authorization, not a roster deletion shortcut.
- The restricted backend cleanup endpoint and recovery copies remain for controlled HR administration; no ordinary directory removal UI is exposed.

## Validation

- Full backend: 1,205 passed, 321 existing integration/environment skips, five existing warnings. A new test initially used an unlinked manager fixture; it was corrected to verify a valid direct manager is denied with 403. The full suite then passed. The final bulk compatibility adjustment also passed all 19 focused status tests.
- Full frontend: 227 passed in 31 suites. Tests verify rows expose only Edit, supported status choices, saving Inactive, preservation of legacy department/identity fields and all existing regressions.
- Strict production build, Python compilation and whitespace checks passed.

## Operational handover

The employee roster is 21 FTEs. One newly added person's start date is a user-authorized placeholder and must be replaced by HR with the confirmed date. No salaries, personal contacts, login credentials or employee roster exports were added to Git. No Solver records were modified. The status release must be deployed to Render and cPanel; browser caches may require a release-specific URL or a hard refresh to display the latest employee page.
