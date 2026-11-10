# Empty-email prevention

## Root cause

The shared email sender substituted the generic subject `Solvit People Platform` and `<p>(no body)</p>` when a message or template was missing. Branding then produced a valid-looking email without actual message content. This matches the screenshot, but the specific originating event or missing production template has not been identified from live logs.

## Fix

- Shared pre-send validation requires a meaningful subject and message body before branding. Rejects whitespace, entities/zero-width whitespace, comments/markup-only messages, style/script/head-only content, unresolved merge-tag-only content and known no-body placeholders. Subjects containing line breaks are rejected.
- Missing templates are skipped with a clear reason rather than replaced with generic content.
- Both SMTP and Sender.net use this guard, including formal messages, manual resends and automatic retries. Existing fixed-content test emails remain unchanged.
- Wrapped messages queued before this release are inspected using their original body, excluding branding. Newly wrapped messages carry explicit body boundaries.
- Invalid queued messages become blocked without generating new retry entries. Valid delivery failures retain the existing retry behavior.
- Template editing rejects empty subject/body before saving. Merge tags remain supported; rendered payloads are validated again at send time.
- Plain-text-only callers are supported with safely escaped HTML.
- Existing outbound-email deployment switch, authentication and permissions remain unchanged.
- Blocks are recorded in the existing email log as skipped with a diagnostic reason and template key; message bodies and credentials are not added to logs.

## Validation

Full backend suite: 1,574 passed, 321 skipped, five existing deprecation warnings.
Full frontend suite: 348 passed across 49 suites.
Python compilation and git whitespace checks passed. No frontend code changed, so frontend builds were not repeated.
Tests cover both providers, missing templates, post-merge emptiness, legacy branded retries, normal template delivery, plain text and template-editor rejection. All delivery transports were mocked; no real email or production database was used.

## Files

- backend/utils/email_content.py
- backend/utils/email_service.py
- backend/routes/email_templates.py
- backend/tests/test_email_content.py
- docs/empty-email-prevention-report.md

## Operations

No migration, credentials or infrastructure changes are required. Main-branch push triggers the existing Render backend auto-deployment. Live completion must be confirmed separately. Existing email templates should be checked through the authorized email-template/log screens for skipped missing/empty templates; this fix intentionally does not invent or overwrite HR-approved message content. Previously delivered emails cannot be recalled by this change.
