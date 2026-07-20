# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security reports. Instead, use GitHub's private vulnerability reporting (Security tab, "Report a vulnerability") on this repository. Include a description, reproduction steps, and the impact you observed. You can expect an initial response within a few days.

## Scope and safety posture

website-ai-agent drives a real browser autonomously, so it is built with fences on by default:

- **Domain allowlist.** Navigation can be restricted to the start URL's domain (`--same-domain`, on by default in the CLI and API). Off-allowlist navigations are dropped by the planner's policy filter before they run.
- **Destructive-action policy.** Actions whose accessible name or type looks state-mutating or destructive (submit, delete, logout, pay) are risk-classified. Safe-explore is the default; destructive actions are not attempted unless explicitly enabled.
- **Secret handling.** API keys and credentials come only from the environment or a storage-state file, never from prompts or reports. Logs and persisted artifacts are redacted at write time for secret-shaped values and credential form inputs.
- **No evasion.** The agent does not bypass CAPTCHAs or bot detection. If a site blocks automation, it reports that and stops.

Intended targets are your own sites, staging environments, and the bundled fixture sites. Do not point the agent at systems you are not authorized to test.

## Supported versions

This project is pre-1.0; security fixes are applied to `main`. Pin a commit or released version for reproducible deployments.
