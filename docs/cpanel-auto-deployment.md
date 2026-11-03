# Frontend automatic deployment

## Status

The repository now contains a GitHub Actions workflow and an encrypted FTPS publisher.
The one-time setup was completed on 3 November 2026. Environment `cpanel-production`
contains the three FTPS secrets and the confirmed public backend origin. Repository
variable `CPANEL_AUTODEPLOY_ENABLED` is `true`. The first manual run succeeded:
https://github.com/Peris25/solvit-people-mgt/actions/runs/41622621239

That run passed 257 frontend tests (35 suites), five publisher tests and the strict
production build, then uploaded seven files and verified the live HTML and JS/CSS.
An independent public check confirmed the flat HR leave queue and absence of the old
pending-day summary text. Future qualifying `main` pushes publish automatically.
No backend deployment or employee-data changes were performed by this setup.

Verified explicit FTPS hostname: `ossa-lon.cloudhosting.uk`, port 21. The cPanel-suggested
`ftp.solvit.co.ke` failed hostname certificate validation; do not substitute it or
disable certificate checks. The dedicated account was created with the People frontend
directory restriction. The environment's additional branch restriction remains an
owner hardening step; the workflow itself only runs deployments from `main`.

## One-time setup

1. In cPanel, open **FTP Accounts**. Create a dedicated deployment account whose
   home directory is exactly `/home/solvitcoke/public_html/people`. Do not use the
   main cPanel account. The operator must enter and submit the new password.
2. Open its **Configure FTP Client** details. Confirm that the provider supports
   explicit FTPS on port 21, passive data connections, trusted TLS certificates and
   rename-over-existing-file. Use the hostname matching the FTPS certificate, not
   the cPanel URL with `https://` or `:2083`. Never bypass certificate validation.
3. In GitHub, open `Peris25/solvit-people-mgt` → **Settings → Environments** and
   create `cpanel-production`. Limit deployment branches to `main`.
4. Add these **environment secrets**, entering values in GitHub rather than chat:

   | Secret | Value |
   | --- | --- |
   | `CPANEL_FTP_HOST` | Provider-confirmed FTPS hostname |
   | `CPANEL_FTP_USER` | Full dedicated FTP username from cPanel |
   | `CPANEL_FTP_PASSWORD` | Dedicated account password |

5. Add environment **variable** `REACT_APP_BACKEND_URL`: the existing production
   HTTPS backend origin, with no `/api`, query string or credentials. Confirm
   against the deployed frontend/backend configuration; do not guess a service URL.
   React build variables are public, so never put secrets in `REACT_APP_*` values.
6. Open **Actions → Deploy frontend to cPanel → Run workflow → main**. Review the
   first run. Confirm its final step verifies the live HTML and referenced JS/CSS,
   then check login, navigation and HR's leave queue in the browser without making
   real leave decisions. Keep the manual upload route until this succeeds.
7. Once the first manual run succeeds, add the **repository Actions variable**
   `CPANEL_AUTODEPLOY_ENABLED` with value `true` under **Settings → Secrets and
   variables → Actions → Variables**. This enables automatic push deployments.
   Leave it unset until setup is verified; the workflow is safely skipped on pushes.
   Set it to `false` to pause automatic publishing without deleting credentials.

If the host does not offer verified FTPS with directory isolation, do not use a
plain FTP fallback. Ask the hosting provider for a restricted SSH deployment option.

## Subsequent releases

Frontend, publisher or workflow changes pushed to `main` trigger installation from
the lockfile, deployment tests, all frontend tests and a strict CI production build.
Backend-only changes do not upload frontend files. Manual workflow dispatch is also
available on `main`. Only compiled build files are published; no employee exports,
reference PDFs, backend files, credentials or source maps are uploaded.

The publisher uses certificate-verified TLS for control and data connections, uploads
temporary files and renames them into place, and publishes `index.html` last. It never
deletes remote files, including `.htaccess` and old hashed assets. The deployment FTP
account is responsible for confining `/` to the People frontend directory. Do not
configure a broader account: the publisher intentionally has no arbitrary target-path
setting. Old release archives/assets may need a separate reviewed cleanup later.

Runs are serialized, with cancellation disabled to avoid interrupting a deployment
mid-write. Network failures fail the job; retry from Actions after resolving them.
Live verification failure does not automatically roll back. Previously published
assets remain available; an operator can redeploy a reviewed known-good frontend
using the manual upload route. The independent root files are not one atomic release,
although the application entry point is published after its assets.

## Validation

- Five unit tests cover upload order, temporary rename, no deletion, forbidden files,
  missing builds, directory creation, live-byte verification and TLS requirements.
- Clean `npm ci --legacy-peer-deps --ignore-scripts` succeeded with the new lockfile
  in an isolated tooling directory (1,479 packages); no application dependencies
  were added to `package.json`.
- The frontend regression suite passed 257 tests across 35 suites before this workflow
  addition; the flat HR queue strict CI build also passed.
- Run `python -m unittest discover -s scripts -p 'test_*.py' -v` locally for publisher
  checks. They use synthetic files and mocked connections, never the production host.
- A real FTPS deployment passed, confirming provider compatibility, credentials,
  encrypted data transfer, remote rename behavior and public HTML/asset verification.
