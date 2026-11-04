# HR draft-review deletion

HR can select Delete draft beside an eligible review, or explicitly select several drafts and Delete selected. The confirmation lists employee names and periods, requires a reason and explicit confirmation, and does not call the API on selection or Cancel.

Server-side requirements: HR performance write permission, canonical tenant-scoped identity resolution, an unchanged version, Draft status and no saved employee assessment, manager/HR assessment, score, signature, meeting or linked form submission. Legacy empty drafts qualify without converting them to the new workflow. Submitted, scored and completed reviews are protected. All records in a batch are checked before any deletion; duplicate selections and foreign records fail closed.

The shared integrity lock serializes deletion against submissions and updates. Metadata-only deletion audit entries are written before removal. Only selected review records, explicitly linked notifications for all recipients, notification receipts and explicitly linked portal tasks are removed. Employee records, other reviews, shared cycles and audit history remain. A deleted draft no longer blocks a replacement review for that period. Removal is permanent through this UI.

If cleanup is interrupted, review-linked notifications whose review no longer exists are hidden rather than becoming generic alerts. Existing controlled persistent-lock recovery still applies to interrupted writes. HR's notification context refreshes after deletion; other browser sessions update on their next fetch/notification poll. Already delivered emails cannot be recalled. Dismissing/marking a notification read does not delete a review; deletion is deliberately initiated from Performance with confirmation.

## Files

`backend/utils/review_deletion.py`, `backend/routes/performance.py`, `backend/utils/performance_workflows.py`, `backend/utils/notification_centre.py`, `backend/tests/test_review_deletion.py`, `frontend/src/services/performanceDeletion.js`, `frontend/src/components/DeleteReviewDialog.js`, `frontend/src/pages/Performance.js`, `frontend/src/pages/Performance.test.js`, and this report.

The separately approved login-logo CSS treatment is also included in `frontend/src/components/Portal.css`: remove the white container and blend the image backdrop into the dark login artwork, scoped to login only. Shared logo assets and authentication behavior are unchanged. Unfinished leave-reconciliation work is excluded.

## Validation

- Full backend: 1,473 passed, 321 skipped, five existing warnings.
- Full frontend: 322 passed across 44 suites.
- Strict CI and normal production builds passed.
- Python compilation and whitespace checks passed.
- Regression coverage includes role isolation, scored/submitted protection, stale versions, legacy drafts, tenant boundaries, selected-only bulk removal, notification/receipt/task cleanup, audit failure, linked-submission protection, orphan alert suppression and replacement creation.
- No production reviews were deleted or created during testing. No migration required. HR must review and confirm actual stale records through the new UI.
