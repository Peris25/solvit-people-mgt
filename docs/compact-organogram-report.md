# Compact reference organogram

The primary Organogram view now follows the supplied Solvit chart: branded heading, Board above Managing Director, lateral Executive Director link, six management branches across, and their team boxes beneath. It uses a scalable SVG with the reference role labels, red boxes and thin connectors, bounded to 70% of viewport height. No employee names or manager assignments are inferred from these role boxes.

The existing live employee reporting tree remains available below in a collapsed section. Searching automatically opens that section and preserves ancestor context. Existing permission checks, API data, employee identities, duplicate/cycle notices, keyboard expansion, error and empty states remain. No employee, department or manager records were changed.

Changed files: `frontend/src/components/CompactRoleChart.js`, `frontend/src/pages/Organogram.js`, `frontend/src/pages/Organogram.test.js`, and this report.

Validation: all 319 frontend tests across 44 suites passed, including seven organogram regressions. Strict CI and normal production builds and whitespace checks passed. No backend change or migration required. Unfinished leave work is excluded from this release.
