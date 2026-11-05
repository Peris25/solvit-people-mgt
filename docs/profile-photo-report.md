# My Profile photo upload

Employees can upload their own JPG/PNG photo from My Profile by choosing the camera icon inside the initials circle. Selecting and uploading a photo records the employee's explicit photo-use action, without a separate checkbox. The UI accepts up to 2 MB and shows upload progress, success and useful failures. The backend additionally limits decoded images to 4 megapixels, validates actual content, scans the original through the existing ClamAV integration and re-encodes a JPEG thumbnail up to 512 x 512 without original metadata.

## Security and storage

Authenticated self-only GET/POST/DELETE `/api/documents/me/profile-photo` resolve the saved canonical or legacy employee link server-side, without a client-supplied employee ID. Ineligible employee accounts and missing/ambiguous links fail closed. Existing password-change, session and MFA enforcement remains active.

Photos use existing private DOC_UPLOAD_ROOT and employee_documents metadata, with random filenames, file permissions, clean-scan status, consent timestamp and upload/view/removal audit events. They become readable only after audit publication. Replacements preserve prior document history. No external photo URL is used and no new storage service, dependency, collection or migration is required.

Photos are displayed on the employee's own My Profile only; Staff Directory and other employees' profile views retain initials. Existing authorized HR document access remains in place. Original employee records and directory consent settings are unchanged.

## Validation

- Frontend: 348 tests passed in 49 suites.
- Strict CI build and normal production build passed.
- Python compilation and git whitespace checks passed.
- Backend: 1,543 passed, 321 skipped, five existing deprecation warnings.
- Coverage includes employee isolation, legacy links, upload authorization, file type/size/dimensions, scanner failure, audit publication failure, storage escape rejection, photo display and soft API error handling.

## Deployment prerequisites

Existing persistent private disk and working DOC_SCANNER_HOST/DOC_SCANNER_PORT configuration are required; scanner failure rejects uploads without publishing files. Existing main-branch cPanel and Render auto-deployments deliver this release. Deployment completion and a real authenticated upload still require live verification; automated tests do not claim live verification. No real employee photo was uploaded during development.

Modified files: backend/routes/documents.py; backend/utils/profile_photos.py; backend/tests/test_profile_photos.py; frontend/src/components/ProfilePhoto.js; frontend/src/components/ProfilePhoto.test.js; frontend/src/pages/EmployeeProfile.js; frontend/src/pages/MyProfile.test.js; frontend/src/services/api.js; this report.

## Compact photo controls

Camera, pencil (replace) and bin (remove) icons are inside the photo circle with accessible names and tooltips. The separate upload button and checkbox are removed. File selection remains JPG/PNG up to 2 MB, with the same backend scanner and dimensional checks.

DELETE removes all of the current employee account's profile photo versions from active display, using the existing integrity-write lock, audit-first soft deletion and tenant/employee/uploader scope. It cannot target another employee or remove unrelated documents, and old photos do not reappear as a fallback. Historical files are retained privately under the existing retention model; this is removal from active use, not permanent filesystem erasure. No live photo was deleted during testing.

Regression tests cover icon state changes, successful and failed removal, prevention of old-photo fallback, employee isolation, audit failure and repeat deletion. Push triggers existing deployment workflows; live completion must still be verified separately.
