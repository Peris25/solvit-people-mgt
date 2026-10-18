# Staging runtime safety controls

These switches are implemented locally. No Render or production configuration has been changed.

For a later approved isolated staging deployment, explicitly configure:

```env
ENABLE_BACKGROUND_JOBS=false
OUTBOUND_EMAIL_ENABLED=false
```

Both switches default to **enabled when unset**, preserving existing production behavior. Explicit `true`, `1`, `yes`, `on` enable; `false`, `0`, `no`, `off` disable, case-insensitively. Empty/invalid values disable safely and log the variable name without its value. Apply consistently to every instance and restart/redeploy through the approved process; these are not database/UI settings.

## Background jobs

When disabled, the automation and reminder engines initialize their database/configuration needs but do not construct/start schedulers or register timer jobs. Reminder settings/rule updates cannot override the deployment switch. An existing scheduler is cleared/paused when initialization or registration is attempted while disabled, and scheduled callback entry points also reject execution.

Event-driven automation, form outcomes, in-app notifications and explicit authorized manual reminder runs remain available. Manual runs are deliberate administrator actions, not scheduled jobs; outbound email remains governed independently. Disabling timers pauses daily checks, scheduled reminders, email retries and automatic approved-exit account deactivation. Test those scheduled behaviors separately in an approved synthetic-data session before enabling timers.

## Outbound email

When disabled, normal and formal-template email returns `status: skipped` and `reason: outbound_email_disabled` before provider/credential selection. A minimal best-effort skip log is retained without copying recipient addresses into suppression records. SMTP and Sender.net transport helpers enforce the switch independently. The separate IT test-email route enforces the same control; manual resend passes through the guarded common sender.

Retry processing does not claim/change pending rows while disabled or create retries for suppression. If a send is suppressed after a retry row was claimed, it is restored to pending. Existing pending messages are preserved; review them before re-enabling email. Ordinary in-app notifications and required workflow audit behavior continue.

Do not rely on a testing/Mailtrap database toggle alone: the existing formal-template override remains for normal production operation. Keep production provider credentials out of staging, even with the deployment switch disabled. Changes do not cancel transmissions already underway in an old enabled process; stop old instances before relying on a new configuration.

## Remaining staging prerequisites

Configure the isolated MongoDB database, MFA enrollment/keys, private persistent upload roots, actual ClamAV-compatible scanner, scanner signatures/health tests, body-size/proxy settings and safe frontend origins. The scanner is not provisioned by this change. Validate clean/malware/outage behavior against the real private scanner before document UAT. The existing global integrity-lock recovery and HR/data reconciliation prerequisites remain unchanged. No migrations or dependency changes are required for these controls.

## Local validation

18 October 2026: `test_runtime_controls.py`, `test_notification_centre.py`, `test_leave_management.py`, `test_lifecycle_workflows.py` and `test_learning_workflows.py`: **195 passed, 3 skipped**, five existing dependency/lifecycle deprecation warnings. All **48 new runtime-control tests passed**; skips are existing real-Mongo concurrency tests because no disposable MongoDB was selected. Python compilation and tracked/new-file whitespace checks passed. Tests used synthetic in-memory repositories and mocked transports; no live email, production database or scheduler was contacted. Frontend/build and full integration suites were not requested or rerun for this backend-only change.
