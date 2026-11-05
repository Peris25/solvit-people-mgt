# My Profile photo upload

Employees can upload their own JPG/PNG photo from My Profile after confirming photo use. The UI accepts up to 2 MB and shows upload progress, success and useful failures. The backend additionally limits decoded images to 4 megapixels, validates actual content, scans the original through the existing ClamAV integration and re-encodes a JPEG thumbnail up to 512 x 512 without original metadata.

## Security and storage

Authenticated self-only GET/POST `/api/documents/me/profile-photo` resolve the saved canonical or legacy employee link server-side, without a client-supplied employee ID. Ineligible employee accounts and missing/ambiguous links fail closed. Existing password-change, session and MFA enforcement remains active.

Photos use existing private DOC_UPLOAD_ROOT and employee_documents metadata, with random filenames, file permissions, clean-scan status, consent timestamp and upload/view audit events. They become readable only after audit publication. Replacements preserve prior document history. No external photo URL is used and no new storage service, dependency, collection or migration is required.

Photos are displayed on the employee's own My Profile only; Staff Directory and other employees' profile views retain initials. Existing authorized HR document access remains in place. Original employee records and directory consent settings are unchanged.

## Validation

- Frontend: 346 tests passed in 49 suites.
- Strict CI build and normal production build passed.
- Python compilation and git whitespace checks passed.
- Backend: 1,541 passed, 321 skipped, five existing deprecation warnings.
- Coverage includes employee isolation, legacy links, consent, file type/size/dimensions, scanner failure, audit publication failure, storage escape rejection, photo display and soft API error handling.

## Deployment prerequisites

Existing persistent private disk and working DOC_SCANNER_HOST/DOC_SCANNER_PORT configuration are required; scanner failure rejects uploads without publishing files. Existing main-branch cPanel and Render auto-deployments deliver this release. Deployment completion and a real authenticated upload still require live verification; automated tests do not claim live verification. No real employee photo was uploaded during development.

Modified files: backend/routes/documents.py; backend/utils/profile_photos.py; backend/tests/test_profile_photos.py; frontend/src/components/ProfilePhoto.js; frontend/src/components/ProfilePhoto.test.js; frontend/src/pages/EmployeeProfile.js; frontend/src/pages/MyProfile.test.js; frontend/src/services/api.js; this report.
