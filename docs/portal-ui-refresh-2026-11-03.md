# HR and employee presentation refresh

## Scope

Frontend presentation only. The release retains all routes, role filtering, event
handlers, API calls, form validation, approval rules, records and authentication gates.
It adds a shared workspace header and a My Profile shortcut to the existing route.

The shared shell now uses a lighter canvas, a sticky independently scrollable sidebar,
clearer active navigation, consistent spacing, cards, typography, form controls and
table styling. HR and employee dashboards use welcome panels. Status badges, focus
indicators and action buttons share the visual language. Responsive rules cover narrow
navigation, dashboard columns, forms and tables; reduced motion and print rules remain.
Dark-theme styles follow the existing theme setting. The notification panel offset is
aligned with the wider sidebar. Solver's separate mobile layout is left intact.

Login uses the local logo and CSS gradients instead of external photo/logo downloads.
Its fields, password visibility, forgotten-password link, login logic and security
controls are unchanged. No additional fonts, image dependencies or runtime packages
were added. The changes intentionally preserve existing module-specific controls.

## Files

- `frontend/src/components/Portal.css`: scoped shared presentation and responsive rules.
- `frontend/src/components/Layout.js`: workspace header, skip link and styling scope.
- `frontend/src/components/Sidebar.js`: visual hooks, icon size and notification offset.
- `frontend/src/components/StatusBadge.js`: shared presentation class.
- `frontend/src/pages/Dashboard.js`: HR header and responsive column hooks.
- `frontend/src/pages/EmployeeDashboard.js`: employee welcome-panel hook.
- `frontend/src/pages/Login.js`: responsive presentation hooks and local assets.
- `frontend/src/components/RequiredPasswordChange.test.js`: router Link mock for the
  header; password-change gate regressions still run unchanged.

## Validation and limits

- Complete frontend suite: **265 passed, 35 suites**.
- Strict CI production build and whitespace checks passed. The automatic deployment
  workflow repeats tests/build and verifies live HTML and referenced JS/CSS bytes.
- A temporary offline fixture rendered the actual HR, employee and leave components
  with synthetic data; rendering succeeded. That fixture was removed from source and
  is not included in this release. Local preview HTML remains ignored.
- Browser automation could not reliably identify the current URL and stopped before
  screenshots could be reviewed. Desktop/mobile/dark visual acceptance is therefore
  **not verified**. Do not describe this release as visually approved or every module
  as individually reviewed. The user explicitly requested deployment after this limit
  was reported. A later live visual pass remains necessary, especially legacy screens
  with inline styles, charts, dialogs and the AI panel.
- No backend, permissions, production data, credentials or database schema changes.

The prior frontend can be restored by reverting this presentation commit and allowing
the same tested automatic deployment workflow to publish the build.
