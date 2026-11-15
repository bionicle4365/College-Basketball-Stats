---
name: espn-analytics-expert
description: Domain rules for ESPN College Basketball APIs (Men's & Women's), Fantasy VAL calculation, BPI/PWR rankings, Quadrant 1-4 cutoffs, and SOS metrics.
---

## ESPN API & Basketball Analytics Rules

### 1. Dual-League Support (`mens` & `womens`)
- Every ESPN fetch helper in [helpers.js](file:///d:/Git/College-Basketball-Stats/site_ui/helpers.js) must accept `sportPath` (`mens-college-basketball` or `womens-college-basketball`) via `getSportPath(league)` and default team ID via `getFavoriteTeamId()` (`152` NC State default).
- Remember that ESPN's FITT `/powerindex` endpoint often returns HTTP 400 for `womens-college-basketball`; `fetchBpiAndResumeMap` falls back to computing national power rankings (`source: 'PWR'`) and SOR from `/standings`. Always preserve this fallback.

### 2. Fantasy VAL Formula (`calculateVal` & `getValDetails`)
- Standard VAL formula:
  `VAL = PTS + 3PM - FGA + (2 * FGM) - FTA + FTM + REB + (2 * AST) + (4 * STL) + (4 * BLK) - (2 * TO)`
- Value tier classes (`getValTierClass(val)`):
  - `val >= 30`: `val-pill-high`
  - `val >= 15`: `val-pill-mid`
  - `val >= 0`: `val-pill-low`
  - `val < 0`: `val-pill-neg`

### 3. NCAA Quadrant 1–4 Cutoffs (`getGameQuadrant`)
- **Home**: Q1 `1–30`, Q2 `31–75`, Q3 `76–160`, Q4 `161+`
- **Neutral**: Q1 `1–50`, Q2 `51–100`, Q3 `101–200`, Q4 `201+`
- **Away**: Q1 `1–75`, Q2 `76–135`, Q3 `136–240`, Q4 `241+`
