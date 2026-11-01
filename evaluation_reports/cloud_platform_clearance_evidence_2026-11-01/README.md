# Bottom bar clears Streamlit Community Cloud's floating controls: evidence (01 Nov 2026)

## Problem and fix

**Problem.** On Streamlit Community Cloud, the hosting page draws its own floating controls at the bottom right of the screen: the viewer badge (top at 754 px, 46 px tall) and the creator avatar. On phones these covered **More** and part of **Safety**.

**Fix.** On `*.streamlit.app` only, at widths of 640 px or less, the bottom bar is raised by the measured height of those controls (52 px here), and only while they are present. Content padding grows by the same amount, and `env(safe-area-inset-bottom)` is kept. Anywhere else, or when the controls are absent, the lift is 0.

The platform controls are only measured; they are never hidden, moved or restyled.

## Live checks

| Check | 360 light | 390 light | 390 dark | 430 light |
|---|---|---|---|---|
| Lift | 52 px | 52 px | 52 px | 52 px |
| Bar position | 685–748, fixed | 685–748, fixed | 685–748, fixed | 685–748, fixed |
| Tabs covered by platform controls | none | none | none | none |
| All five tabs tappable, 54 px, untruncated | yes (69 px wide) | yes (75 px) | yes (75 px) | yes (83 px) |
| Bar unchanged after scrolling to the end | yes | yes | yes | yes |
| Last content above the bar (bottom / bar top) | 660 / 685 | 660 / 685 | 660 / 685 | 660 / 685 |
| Horizontal overflow / exceptions | none / 0 | none / 0 | none / 0 | none / 0 |
| More sheet and ☰ open | yes | yes | – | yes |

These results come from two runs:
- **`live_pre_merge/`**: the branch's exact CSS declarations and clearance script were injected into the live page before merging.
- **`live_deployed/`**: the deployed code after the push (`1f51265`), with the deployed stylesheet confirmed to contain the fix.

Both gave the same results.

Tablet (820 px) and desktop (1366 px) on the deployed app: no phone bar, sidebar layout, no exceptions or overflow. These layouts are unchanged.

## Tests

`test_run1.txt` and `test_run2.txt`: 415 passed. Run 2 used the network guard (0 outbound attempts).

Model logic, the 29 inputs, the 35% threshold, and the warning, offline and SMS behaviour are unchanged.
