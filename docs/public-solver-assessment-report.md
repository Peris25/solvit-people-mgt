# Public new-Solver questionnaire ? 3 November 2026

## Source and scope

The user approved portal-based collection rather than embedding Google Forms. Source: https://forms.gle/omWVaTi8MTAJyyPQA (Motor Vehicle Solver Assessment). Read only the public form/question schema; no Google responses or credentials were accessed and no Google Form was submitted.

The local version contains 23 applicant questions from the source, including original required flags, rating scales and options. The ExtendedForms tracking field is omitted because it is an external-vendor integration identifier, not a candidate question. The experienced-valuation question is skipped when the source routing answer is No; subsequent source sections remain available. Questions that mention recording are paragraph responses in the source; no audio capture or upload has been invented.

**Known content gap:** one required presentation question uses two source photos. Their public download endpoints redirect to Google authentication, so the photos have not been copied or substituted. The question remains visibly pending; no answer is accepted or invented. Both the applicant receipt and HR screen flag follow-up. Supply the two approved image assets to complete this question before using the questionnaire as a complete assessment. No automatic pass/fail or certification is provided.

## Implemented

- Anonymous questionnaire at `/solver-assessments`; `?new=1` also allows a signed-in HR user to preview the public form. Authenticated users retain their existing protected assessment workspace.
- Three explicitly registered anonymous API handlers: questionnaire, signed verification challenge, and submission. Existing attempts, results, question banks and HR administration retain authentication/MFA/password gates.
- Required-field, option, version, input-length, consent and bounded-stream validation. Unknown fields, forged identities and scores are rejected.
- Signed two-hour verification challenge, minimum fill delay, honeypot, per-worker challenge throttle and a database-backed five-submissions-per-IP/hour limit using built-in `_id` uniqueness. Network identifiers are HMAC hashed, not stored in plaintext. The existing proxy/IP helper is reused; edge/WAF rate limiting is recommended against distributed abuse and forwarded-header spoofing.
- Idempotent submission retries using a token-derived unique ID and immutable payload digest. Audit and HR notification publication use deterministic IDs and retry-safe upserts. Answers are stored privately in `public_solver_assessments`, separate from employee/Solver account records and assigned assessment attempts. No migration or index installation is required for correctness.
- HR Admin, HR Manager and General Manager can list submissions, view full answers and record review notes. Access also requires the existing unrestricted M02/M03 grants. No other role, anonymous caller or different tenant can retrieve these applications.
- Audit events for receipt, viewing and review; private HR notifications deep-link to the corresponding application. No external email or SMS delivery added.
- Submission never creates an employee, Solver or login, changes existing results, activates a Solver or infers a pass mark. Existing onboarding and configurable Parts A/B assessments remain separate and unchanged.
- Applicant loading/error/retry/receipt states, preserved answers on verification refresh, responsive Solvit styling, consent and accessible question controls. Anonymous calls use a separate HTTP client and cannot trigger session-refresh/login redirects.

## Validation

- Full backend suite: 1,347 passed; 321 existing integration skips (no production database used).
- Full frontend suite: 275 passed across 38 suites.
- Strict CI and normal production builds, changed Python compilation and whitespace checks: passed.
- New tests cover anonymous routing, protected-route isolation, required/unknown/forged answers, invalid/expired verification, consent, idempotent retries, persistent submission limits, tenant/role restrictions, HR review, public/private frontend routing, receipts and preserved input.

## Operational notes

Existing Google Forms answers remain in Google Forms; no historical-response import or cross-system synchronization is included. HR sees the latest 500 ready submissions in the initial review view. Older stored submissions are retained; pagination/export can be added if volume requires it.

HR must define applicant-data retention. Rate-limit slot documents also need a separately approved periodic retention policy; this release deletes no records and installs no TTL indexes. Submission publication interrupted before audit/notifications finish can be recovered by retrying the same form token and identical answers within its two-hour validity. Other operational recovery should be performed by an authorized operator after inspection; no automatic record cleanup is included.

Deploy both services on the same release, then verify the public page in an incognito session and private HR review. Do not create a fictitious production applicant merely to test: local synthetic tests cover submission. Production live acceptance and authenticated browser inspection remain separate verification steps.


## Standalone-only correction requested by HR

The applicant URL `/solver-assessments` now always renders the public questionnaire outside the portal AuthProvider, NotificationProvider and Layout. It is identical for logged-out applicants and already-signed-in HR. No query parameter, Solver record, account, login check, existing-Solver picker, assessment configuration or assignment is needed.

HR's new private route is `/solver-assessment-applications`, reached through **Solver Applications** in the sidebar. It reads only the new public applicant collection. Notifications and Staff Home link to this inbox. Existing-Solver assignment/history screens are no longer routed from the application, old pending assessment tasks and links have been removed from Staff Home and Solver navigation, and the legacy assignment-creation API returns authenticated HTTP 410. Old assignment notifications no longer link into this flow.

This is a fresh applicant workflow: old assigned-assessment answers and Google Forms responses are not imported, listed or reused here. No database purge was performed or claimed; removing unknown stored historical rows is a separate destructive operation, outside this UI/workflow correction.

Regression validation: full backend 1,348 passed / 321 existing integration skips; full frontend 277 passed across 38 suites. Strict and normal production builds, Python compilation and whitespace checks passed. Added checks prove the standalone route never mounts portal authentication and the old assignment endpoint cannot create attempts. The photo-source gap above remains unchanged.


## Answer-view controls and hiring-lead access

- Each applicant row now toggles **View answers / Close view**, with Eye/Close icons, distinct open-state styling, keyboard focus treatment and `aria-expanded` / `aria-controls`. Closing hides the details and clears the note draft without issuing another read. The detail footer also offers Close view. Search, refresh, public-link and table controls use matching responsive styling.
- HR retains applicant access and formal review. The Operations Coordinator / Head of Solvers and Technical Services & Growth Manager positions (the approved Brian/Timothy responsibilities) also receive read-only applicant access, provided the account is an active, canonically linked full-time employee with the Line Manager role and an eligible M03 grant. Authorization resolves the saved employee identity and job title; no personal names/emails are hardcoded into permission checks.
- Other line managers, employees, Solvers, IT and unrelated tenants remain denied. Runtime M03 revocations are honored. No employee salary, bank, medical or other HR-wide permissions are granted by this change.
- A protected capabilities endpoint controls inbox rendering and shows the sidebar entry only for an eligible manager. HR's internal review notes are redacted for hiring leads, and the review-write endpoint still requires HR. Public form access is unchanged.
- Full backend: 1,354 passed / 321 existing integration skips. Full frontend: 279 passed across 38 suites. Strict CI and normal production builds, Python compilation and whitespace checks passed.
- Live Brian/Timothy acceptance remains dependent on their saved employee links, job titles and Line Manager account roles; no account passwords or production employee records were changed. The source photo question still needs its two original images.
