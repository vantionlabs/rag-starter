# Auth setup and escalation path

Auth lives in this FastAPI backend (fastapi-users). One database, one
migration system, users in your own Postgres. No external identity
provider, no second language owning identity.

## How it works

- **Users** live in the `users` table (Alembic-managed, UUID ids). Register
  / login / password hashing (argon2 via pwdlib) all run through
  fastapi-users.
- **Session = httpOnly cookie.** Login (`POST /auth/jwt/login`) sets a
  cookie holding a JWT signed with `AUTH_SECRET`. The token is **never
  exposed to JavaScript**, so XSS cannot steal it. The browser sends it
  automatically on same-site requests.
- **CSRF** is handled by `SameSite=Lax`: the cookie rides along on requests
  from the frontend to the API but not from a third-party site. This
  requires the frontend and API to share a registrable domain (see below).
- **Verification** is local: `get_current_user` (app/auth/dependencies.py)
  is the single seam the rest of the app depends on. It returns
  `CurrentUser{id, email}` and nothing else.

## Configuration

Backend `.env`:

```
AUTH_SECRET=<long random string>       # signs the session JWT
AUTH_TOKEN_LIFETIME_SECONDS=604800     # 7 days
AUTH_COOKIE_SECURE=false               # true in production (HTTPS)
# AUTH_COOKIE_DOMAIN=.example.com      # shared parent domain in production
AUTH_COOKIE_SAMESITE=lax
ALLOWED_ORIGINS=http://localhost:3000  # exact frontend origin(s)
```

Frontend needs only `NEXT_PUBLIC_API_URL`. It sends `credentials: "include"`
on every call; there is no token handling in the browser at all.

## Deployment requirement (important)

For the `SameSite=Lax` cookie to work cross-origin, the frontend and API
must be on the **same registrable domain**:

- Good: `app.example.com` (frontend) + `api.example.com` (API), cookie
  `Domain=.example.com`. Same site → cookie is sent, CSRF is blocked.
- Local dev: `localhost:3000` + `localhost:8000` are same-site (localhost),
  so it works with `AUTH_COOKIE_SECURE=false`.
- Genuinely different sites (`app.com` + `api.io`) would need
  `SameSite=None; Secure` **and** a CSRF token. Avoid this; put both under
  one domain instead.

## Escalation path (SSO, OIDC, multi-tenancy)

The `get_current_user` seam is deliberately swappable. Escalate without
touching anything downstream:

- **Social login / generic OIDC** (Google, Auth0, Okta-via-OIDC, Azure AD):
  fastapi-users supports this through `httpx-oauth`. Add the OAuth account
  table mixin + the OAuth router; it's a config-and-migration change, not a
  rewrite. Wire the provider in `app/auth/backend.py`.
- **Enterprise SAML SSO + SCIM directory sync, EU data:** fastapi-users has
  no SAML. Self-host **Keycloak** or **Authentik** (open-source IdP; does
  OIDC *and* SAML *and* SCIM) as one more Railway service, in the EU. Then
  reimplement ONLY `get_current_user` to verify the IdP's OIDC token against
  its JWKS. WorkOS is the same swap if you accept
  US-hosted identity.
- **Multi-tenancy / orgs:** a data-model change, largely independent of the
  auth library. Add an `organizations` table and a membership table, carry
  the active org on `CurrentUser`, add `org_id` to the document and chunk
  tables, and filter retrieval and the `require_*_access` helpers in
  `app/auth/access.py` on it.

## Password reset and email verification

Not mounted, because both need to send email. To add them:

1. Pick an email provider and write a small `send_email(to, subject, html)`.
2. Implement `on_after_forgot_password` and `on_after_request_verify` in
   `app/auth/users.py` to email a link to `FRONTEND_URL` with the token.
3. Mount `fastapi_users.get_reset_password_router()` and
   `fastapi_users.get_verify_router(UserRead)` in `app/main.py`.
4. Add `/reset-password` and `/verify-email` pages to the frontend.
