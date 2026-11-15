---
name: site-ui-expert
description: Domain rules for College-Basketball-Stats Jekyll pages, Vanilla JS/CSS, Dark Mode, Service Worker PWA caching, and XSS/CSP safety.
---

## Site UI & PWA Architecture Rules

### 1. Security & XSS Prevention
- Always sanitize dynamic strings interpolated into HTML templates using `escapeHtml(str)` and URLs using `sanitizeUrl(url)` from [helpers.js](file:///d:/Git/College-Basketball-Stats/site_ui/helpers.js).
- Preserve the `Content-Security-Policy` meta tag in [default.html](file:///d:/Git/College-Basketball-Stats/site_ui/_layouts/default.html).
- Never overwrite `FIREBASE_*_PLACEHOLDER` tokens in [common.js](file:///d:/Git/College-Basketball-Stats/site_ui/common.js).

### 2. Responsive Layout & Dark Mode
- All UI components in [styles.css](file:///d:/Git/College-Basketball-Stats/site_ui/styles.css) must support both desktop tables and mobile cards/drawers, and must define `.dark-mode` overrides so text contrast remains legible in dark mode.
- Support `?mock=live` and `?mock=pre` query parameters on [scoreboard/index.html](file:///d:/Git/College-Basketball-Stats/site_ui/scoreboard/index.html) without requiring Firebase authentication (`checkAuth()` bypasses auth redirect when `mock` or `demo` query params are set).

### 3. Shared Helpers & Contract Sync
- Put reusable pure computation and formatting helpers in [helpers.js](file:///d:/Git/College-Basketball-Stats/site_ui/helpers.js) so they can be shared across pages and tested deterministically via Node in `tests/test_helpers_and_contracts.py`.
- Whenever a top-level function is added to or removed from `site_ui/helpers.js`, update `helper_functions` in [schemas_and_routes.json](file:///d:/Git/College-Basketball-Stats/docs/contracts/schemas_and_routes.json).
