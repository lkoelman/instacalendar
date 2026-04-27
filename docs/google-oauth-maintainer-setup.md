# Google OAuth Maintainer Setup

This document is for project maintainers who want release builds of
Instacalendar to support:

```bash
uv run instacalendar init --default-export google --google-auth
```

without asking normal users to create their own Google Cloud OAuth client.

## What Instacalendar Needs

Instacalendar is a desktop CLI that writes approved events to a user's Google
Calendar. It uses Google's installed-app OAuth flow through
`google-auth-oauthlib` and requests only this scope:

```text
https://www.googleapis.com/auth/calendar.events
```

Google describes this scope as access to view and edit events on calendars the
user can access. Do not add broader scopes unless the implementation changes.

References:

- Google Calendar API scopes:
  <https://developers.google.com/workspace/calendar/api/auth>
- Installed app OAuth flow:
  <https://developers.google.com/identity/protocols/oauth2/native-app>
- Sensitive scope verification:
  <https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification>

## Create the Google Cloud Project

1. Open Google Cloud Console and create or select the project that should own
   Instacalendar's OAuth identity.
2. Enable the Google Calendar API for that project.
3. In Google Auth Platform, configure the app branding and OAuth consent screen.
4. Use the public project/app identity users should see when authorizing
   Instacalendar.
5. Add the app homepage, support email, developer contact email, privacy policy,
   and terms links if the app will be used by anyone beyond local test users.

## Configure OAuth Audience and Scopes

1. Keep the publishing status in Testing while developing.
2. Add maintainer/test Google Accounts as test users.
3. Add only the `calendar.events` scope:

   ```text
   https://www.googleapis.com/auth/calendar.events
   ```

4. When ready for public use, move the app toward production publishing and
   complete Google's OAuth verification if required.

Notes:

- Google may show tester or unverified-app warnings before verification.
- Testing-mode refresh tokens can be subject to Google testing restrictions, so
  do not treat testing mode as production-ready.
- OAuth verification is separate from package release checks; complete it before
  presenting the Google export flow as frictionless for public users.

## Create the Desktop OAuth Client

1. In Google Auth Platform, open Clients.
2. Create an OAuth client.
3. Choose application type `Desktop app`.
4. Name it something explicit, for example `Instacalendar Desktop CLI`.
5. Download the client JSON.

The downloaded JSON should have this shape:

```json
{
  "installed": {
    "client_id": "...apps.googleusercontent.com",
    "project_id": "...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "...",
    "redirect_uris": ["http://localhost"]
  }
}
```

## Add the Client to Release Builds

Instacalendar looks for a bundled resource named:

```text
src/instacalendar/google-oauth-client.json
```

To ship the maintainer-owned OAuth client:

1. Save the downloaded desktop client JSON at that path.
2. Confirm the file is included in package and PyInstaller release builds.
3. Keep `GOOGLE_OAUTH_CLIENT_JSON` and `GOOGLE_OAUTH_CLIENT_FILE` support in
   place for development, private forks, and emergency client replacement.

Before committing or publishing the file, confirm the OAuth client belongs to
the intended Google Cloud project and consent screen. If the client is revoked,
disabled, or deleted later, released builds that contain it will no longer be
able to complete new Google authorization flows.

## Local Verification

From a clean app home, run:

```bash
export INSTACALENDAR_HOME="$(mktemp -d)"
uv run instacalendar init --default-export google --google-auth
```

Expected result:

1. The CLI opens or prints a Google authorization URL.
2. The consent screen shows the intended app name and project identity.
3. The requested permission is limited to Google Calendar event access.
4. After consent, this file exists:

   ```text
   $INSTACALENDAR_HOME/data/google-token.json
   ```

5. A later Google export reuses or refreshes that token instead of asking for a
   client JSON.

Also verify the developer override path still works:

```bash
export GOOGLE_OAUTH_CLIENT_FILE=/path/to/oauth-client.json
uv run instacalendar init --default-export google --google-auth
```

## Release Checklist

- Google Calendar API is enabled in the OAuth client project.
- Consent screen branding, support email, privacy policy, and developer contact
  are current.
- Only `https://www.googleapis.com/auth/calendar.events` is configured and used.
- OAuth verification is complete or the release notes clearly state the app is
  limited to configured test users.
- `src/instacalendar/google-oauth-client.json` is present in the release build.
- `uv run pytest tests/test_google_auth.py tests/test_cli.py tests/test_runner.py`
  passes.
- A clean `INSTACALENDAR_HOME` smoke test completes the browser auth flow.
