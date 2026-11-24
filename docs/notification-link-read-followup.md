# Notification links and read status ? 24 November 2026

Notifications use the existing tenant, recipient, role and source-record authorization checks. Explicit targets that no longer exist or are inaccessible are omitted without deleting source history. Published policies must be available to the recipient. Form sign-off alerts must match a current authorized pending task.

The bell and Notifications page share an internal route validator and read-and-open helper. Performance review, peer review and Alignment Survey destinations are supported. Policy links open the selected authorized document; form alerts select the assigned queue row. This does not add a form-signing interface.

A normal click saves the personal read receipt before navigating. On success the shared badge updates immediately and refreshes in the background. On failure the user sees an error and can retry. Read receipts are per account, including role broadcasts; one reader does not clear another person's unread badge. Reading does not approve leave, submit a review or complete a task. Read alerts remain in history; a distinct later event can create another unread alert.

Verification uses synthetic records with outbound email disabled. No real notifications were sent or marked read. The Mongo concurrency integration test requires a local Mongo instance and is skipped when unavailable. Production deployment is verified separately from authenticated user acceptance.
