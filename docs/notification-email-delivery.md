# Email copies of bell notifications

New inbox items are checked every 30 seconds by the existing automation scheduler.
Delivery does not depend on anyone opening the application. The worker projects
each item through the same recipient authorization and safe previews as the bell,
then sends its title, summary and a link to `/notifications` using the configured
email provider. Existing bell items and read receipts are unchanged.

The first startup records a durable rollout timestamp in `system_settings`.
Older inbox history is not replayed. Unprocessed new items remain in
`notifications` across restarts, with `email_delivery_checked` set after handling.
The worker processes up to 100 items per pass. Delivery latency increases with
mailbox volume and the existing provider throttle.

Existing leave, automation and performance event claims are reused to prevent
duplicate email copies. Direct legacy self-assessment and initial employee
training templates retain their existing delivery path. SMTP-failure alerts stay
in the portal to prevent an email-failure feedback loop.

Both `ENABLE_BACKGROUND_JOBS` and `OUTBOUND_EMAIL_ENABLED` must allow delivery.
Email provider configuration and testing/production mode continue to come from
Settings → Email Delivery. Missing provider configuration leaves items pending;
normal SMTP failures use the email service's existing retry queue and logs.
No provider credentials or deployment flags are changed by this implementation.

Deployment: ship the backend changes and restart the API. Startup creates the
notification delivery index and rollout marker and registers the scheduled job.
Verify a newly created, authorized notification reaches a test mailbox and
appears in Email Delivery logs before confirming production delivery.
