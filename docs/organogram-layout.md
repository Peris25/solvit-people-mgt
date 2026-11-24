# Employee organogram

The Organogram page contains one custom SVG employee diagram. The previous static role-reference renderer and nested-list renderer have been removed. People and edges come exclusively from the existing authorized organogram API. A Board of Directors box is drawn only when an explicit, resolved board reporting relationship is supplied. Unresolved roots stay separate; the diagram does not guess missing assignments or change saved employee records.

The MD/root sits above the next tier of team leaders. Their teams use compact cards and separate reporting rails to contain the width; vertically stacked siblings remain connected to their actual manager rather than to each other. The default fits the available page width, without horizontal scrolling or enlargement of small teams. Managers can expand/collapse their branch, and keyboard users can do the same with Enter or Space. Search retains ancestor context and a matched manager's team. Team focus, whole-company reset, zoom, fullscreen and full-name/title details are available without another API request.

Validation includes real-parent edge checks, card non-overlap and canvas bounds, explicit board links, search, focus, keyboard interaction and fit controls. The SVG was rendered and visually inspected with a synthetic 23-person hierarchy; synthetic staff are not stored or used in production.
