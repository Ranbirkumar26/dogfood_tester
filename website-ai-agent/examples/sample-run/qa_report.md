# QA Report: sample-run

- Stop reason: `frontier_exhausted`
- Steps: 6
- Pages visited: 4
- Findings: 8
- Tokens: 0
- Cost: $0.0000

## Findings by severity

| Severity | Count |
|---|---|
| Blocker | 0 |
| Critical | 0 |
| Major | 6 |
| Minor | 2 |
| Info | 0 |

## Findings

| Severity | Kind | Page | Detail |
|---|---|---|---|
| major | console_error | http://demo.local/index.html | fixture-console-error-marker |
| major | console_error | http://demo.local/index.html | Failed to load resource: the server responded with a status of 404 (File not found) |
| major | console_error | http://demo.local/missing-page.html | Failed to load resource: the server responded with a status of 404 (File not found) |
| major | http_error | http://demo.local/index.html | GET http://demo.local/missing.json -> 404 |
| major | http_error | http://demo.local/missing-page.html | GET http://demo.local/missing-page.html -> 404 |
| major | missing_label | http://demo.local/contact.html | textbox (input) has no label, aria-label, or accessible text; screen readers cannot announce it |
| minor | dead_action | http://demo.local/index.html | click on e1 produced no observable change |
| minor | dead_navigation | http://demo.local/missing-page.html | the page exposes nothing to click, fill, or navigate; it may be a dead end |
