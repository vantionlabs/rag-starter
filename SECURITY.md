# Security

## Reporting a vulnerability

Email **hello@vantion.co** with "Security" in the subject. Include a
description, the affected commit, and steps to reproduce. Please do not open
a public issue.

We aim to reply within a few working days, confirm the issue, agree a
disclosure date with you, and credit you in the release notes unless you
prefer not to be named.

## Scope

In scope: code in this repository, including auth and session handling, access
checks between users, webhook signing, presigned uploads, and prompt injection
that gets past the citation validator.

Out of scope: vulnerabilities in dependencies (report those upstream) and
issues that need a misconfigured deployment, such as a leaked `AUTH_SECRET` or
a public database.

## Running it safely

- Set a long random `AUTH_SECRET` and `WEBHOOK_SECRET`, and keep
  `AUTH_COOKIE_SECURE=true` outside local development.
- Restrict `ALLOWED_ORIGINS` to your frontend.
- Keep the R2 bucket private; the app only hands out short-lived presigned URLs.
- Treat uploaded documents as untrusted input. The agent is instructed to
  treat retrieved text as evidence, never as instructions, but review what
  your tools can do before giving the agent new ones.
