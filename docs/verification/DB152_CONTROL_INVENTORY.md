# DB-152 — application control inventory

Source audit covers application TSX, shared components and all feature areas. Public marketing controls retain their presentation contract. Counts are source instances, not rendered DOM totals.

| Area | Actions | Icons | Fields | Content/structural buttons |
|---|---:|---:|---:|---:|
| appointments | 1 | 0 | 0 | 0 |
| auth | 19 | 0 | 26 | 1 |
| booking | 10 | 0 | 0 | 2 |
| communications | 48 | 9 | 14 | 1 |
| customer-portal | 43 | 4 | 27 | 12 |
| customer-pricing | 2 | 0 | 0 | 0 |
| customers | 99 | 8 | 42 | 5 |
| dashboard | 127 | 13 | 42 | 24 |
| driver-portal | 13 | 2 | 2 | 0 |
| external-services | 34 | 1 | 6 | 0 |
| fleet | 195 | 18 | 70 | 17 |
| garage | 31 | 8 | 24 | 0 |
| global-search | 2 | 1 | 1 | 0 |
| inventory | 157 | 10 | 65 | 18 |
| invoice-access | 13 | 0 | 1 | 0 |
| maintenance | 47 | 0 | 15 | 0 |
| mechanic-portal | 57 | 1 | 10 | 17 |
| mechanics | 15 | 2 | 13 | 5 |
| operation-execution | 12 | 0 | 0 | 0 |
| parts-pricing | 19 | 1 | 8 | 0 |
| payments | 30 | 2 | 15 | 7 |
| platform-admin | 27 | 6 | 11 | 3 |
| quote-approval | 8 | 0 | 1 | 0 |
| repair-orders | 162 | 32 | 60 | 32 |
| reviews | 16 | 0 | 1 | 3 |
| service-checklists | 6 | 3 | 1 | 1 |
| services | 1 | 0 | 1 | 0 |
| shared | 19 | 29 | 11 | 7 |
| suppliers | 16 | 0 | 3 | 0 |
| vehicle-issues | 17 | 2 | 0 | 1 |

Totals: {"icon":152,"field":470,"action":1246,"content":156}.

Select triggers reuse BaseSelect/PlatformSelect and ShopWorkSelect with the same geometry marker. Checkbox, radio, file, range and color inputs remain native. Structural buttons include records, tiles, switches, navigation, calendar cells and expandable sections; they are explicitly marked content and retain their own layout. Button-shaped links also consume the action geometry.

The initial audit found 1,563 native buttons across 172 files. The migration removes 688 repeated Tailwind height/vertical-padding tokens. Remaining surface CSS supplies color, emphasis and layout; shared geometry takes precedence in a named CSS layer. Build-time lint:controls rejects new native buttons/text-like inputs outside primitive internals and the public landing page.
