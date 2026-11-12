# 360 colleague selector

12 November 2026.

The Forms → Form 26 popup and Performance share a colleague selector. Choices come from the authenticated employee's existing peer assignments, not an unrestricted employee list. Only open, unsubmitted assignments within their collection dates can be selected. Business role/department help distinguish names. Self, inactive and restricted board-only subjects are excluded. The backend checks ownership and current eligibility again on submission.

Changing colleague clears unsaved ratings to prevent attributing answers to the wrong person. Submitted assignments disappear from available choices. Loading, empty, error, retry and success states are explicit. An empty list means HR must confirm cycle dates and assignments; this change does not open cycles or nominate colleagues automatically.

The screenshot showed the older standalone 1–5 form. Its replacement uses the approved V3 0–10 scale and existing five questions, retention choice and anonymous comment. No historical scores are converted. Responses go to the existing V3 peer-response collection and feed the selected employee's Section B. Legacy standalone Form 26 create/submit/sign paths are blocked from creating parallel identified responses. Historical form records are preserved read-only.

Files:

- backend/routes/forms.py
- backend/utils/performance_v3_peers.py
- backend/tests/test_peer_review_selector.py
- frontend/src/components/PeerReviewSelector.js
- frontend/src/components/PeerReviewSelector.test.js
- frontend/src/components/PerformanceV3Panel.js
- frontend/src/pages/Forms.js
- frontend/src/pages/FormsPeerReview.test.js

Validation:

- Full backend: 1,712 passed, 321 existing skips, five existing deprecation warnings.
- Full frontend: 370 passed in 54 suites.
- Strict CI and normal production builds passed.
- Python compilation and whitespace checks passed.
- Tests use synthetic repositories; no production data writes, account changes or migrations were performed.

Deployment is through the existing main-branch auto-deployment workflows. Live deployment status is reported with the release response; no authenticated live submission is made as a test.
