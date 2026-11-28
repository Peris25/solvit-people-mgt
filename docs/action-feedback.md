# Submission and action feedback

28 November 2026

- Shared ActionButton associates visible prerequisite guidance with blocked actions using aria-describedby. Explanations use the existing screen conditions; permissions, approval rules, five-colleague minimum, and submission payloads are unchanged.
- Sixty-seven prerequisite actions now explain missing selections/files, minimum colleague count, unavailable records, review prerequisites, acknowledgement, required reasons, pending requests and capacity limits across the portal. Paging boundaries, zoom limits and decorative disabled inputs are not validation errors.
- FormValidationFeedback listens for native invalid events on all routes. It renders a persistent summary within the affected form, names the invalid fields, deduplicates radio groups, and focuses the first invalid control. Links return users to each field. Corrected errors disappear as input changes without moving the user's typing focus. It does not add requirements or block draft saves.
- API mutation failures (including offline/network failures and 4xx prerequisites) emit an action message while preserving the existing rejection/local error handling. Server failures keep their existing response contract. Authentication gates and deliberate request cancellations use their existing handling.
- Action messages remain until dismissed, omit endpoint paths and internal server diagnostics, and advise users to check record status before retrying an uncertain submission. Success is not inferred from an HTTP request being started.

Regression tests cover field correction and focus, radio groups, exact peer-review prerequisite counts, ARIA association, retained input/draft behavior, mutation errors and internal error redaction. No real staff records, reviews, messages or approvals are submitted during checks.
