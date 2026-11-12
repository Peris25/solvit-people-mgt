# Performance improvements — 12 November 2026

Changes:

- SMTP transactions run in a worker thread, so a slow mail server cannot block
  unrelated asynchronous API requests. Provider selection, throttle, disabled
  delivery checks, logs and retry behavior remain in the existing pipeline.
- Permission overrides and custom roles are fetched concurrently. Both still
  come from the primary database on every request; there is no permission cache.
- Authorized employee profile sections load concurrently instead of serially.
  Section limits and projection rules are preserved. Notification reads also
  retain an explicit tenant constraint.
- Notification emails select plausible account recipients before doing full
  inbox authorization. One targeted staff notice now projects its one candidate
  rather than every staff account. Legacy employee aliases and account links
  remain supported; authorization is still required before sending anything.
- AI assistant, public assessment and individual role dashboards load on demand.
  Route loading stays within the content area, preserving navigation.
- Employee search waits 250 ms after typing stops before requesting results.
  Filters refresh without blanking an already loaded table; failed requests keep
  the current rows with a retry option.

Measurements:

| Check | Before | After |
| --- | ---: | ---: |
| Initial production JavaScript, raw bytes | 434,212 | 416,781 |
| Initial production JavaScript, gzip bytes | 133,907 | 129,258 |
| Controlled profile query stage, median ms | 194.7 | 35.4 |

The profile benchmark uses synthetic records, six independently delayed section
reads (20 ms configured delay each), and five runs per mode. It compares serial
and concurrent scheduling of the same section reads. It is not a production
page-load measurement or a guarantee of an equivalent overall speedup.

Checks cover SMTP/event-loop responsiveness, overlapping section/configuration
reads, account and tenant isolation, existing email controls, debounced search,
visible navigation during lazy loading, and the production build.

Deploy both backend and frontend to obtain all improvements. Hosting startup,
database/network latency and provider response time can still affect live speed.
