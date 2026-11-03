# Portal performance improvements ? 3 November 2026

## Findings and changes

1. All business pages were statically imported into the initial browser bundle. Business routes now load on demand behind the existing authentication/layout and access gates, with an accessible loading message. Login, recovery and security controls remain available. Existing FTPS deployment retains previous hashed assets, supporting browsers already running a prior release.
2. Employee identity lookups repeated within read-only requests. A ContextVar memo now reuses employee lookup results only during one GET/HEAD request. It is tenant/database/reference scoped, returns independent copies and is discarded at the request boundary. Writes do not enable the memo. Account activation, token/session invalidation, MFA and persisted permissions are not cached across requests or workers.
3. Notification authorization/link checks were serial over the entire inbox. These now run in bounded batches of six. Every item still passes recipient and related-record authorization before counts, sorting, filters or paging. Unread counts remain exact; private previews stay redacted. No stored notifications were changed.

## Measured evidence

- Initial compressed JavaScript: 259.39 KB before; 131.23 KB after (49.4% reduction). Pages still download their own chunks when opened; this is not a claim that all end-to-end page loads are 49% faster.
- Synthetic employee read test: 40 repeated reads use one lookup query instead of 40, with a fresh query on the next request. Tenant/concurrent-request boundaries and duplicate detection outside the read context are covered.
- Notification test verifies more than one but no more than six simultaneous checks, exact unread totals, descending order and exclusion of unauthorized records.

## Validation

- Full backend: 1,333 passed, 321 existing integration skips. No production database or credentials used for tests.
- Full frontend: 270 passed across 37 suites, including actual lazy-route navigation.
- Strict CI build and normal production build: passed.
- Changed Python compilation and Git whitespace checks: passed.

## Deployment and remaining measurement

No dependencies, production indexes, stored employee records, balances, permissions or workflow rules changed. Publish through the existing frontend and backend auto-deploys. Verify both services run the release before judging backend gains.

Authenticated production browser timing remains unmeasured because the browser connection was unavailable. Hosting cold starts, geographic network latency, MongoDB query/index performance and large historical datasets may still contribute. These require live timing evidence before changing hosting plans or installing indexes. Do not replace fresh multiworker authorization with a worker cache to improve speed.
