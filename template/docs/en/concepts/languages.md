# Languages

Keelstone projects speak the languages chosen with the Copier question `languages` (English is
always included, Italian is the default second language). This page explains where each
language comes from and how to add a text.

## Which language is used

The backend chooses the language of each request in this order, and the first one available
wins:

1. the user's saved preference (`locale`, editable from the profile);
2. the default of the active organization (`default_locale`);
3. the `Accept-Language` header, which the frontend sends with the language of the interface;
4. English.

The language applies to error messages and to emails. Emails go out in the recipient's saved
language when it is known, otherwise in the language of the request; invitations use the
organization's default, because the invited person may have no account yet.

## Errors

Every error is a Problem Details document (RFC 9457), served as `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Non autorizzato",
  "status": 401,
  "detail": "Non autenticato",
  "code": "AUTHENTICATION_ERROR",
  "request_id": "0f6c..."
}
```

`title` and `detail` are translated and the response carries `Content-Language`. Clients
should branch on `code`, which never changes with the language.

## Adding or changing a text

| Where | How |
| --- | --- |
| Backend errors | Raise an `AppException` subclass with an English message; the message is the key. For texts defined away from where they are shown, wrap them in `N_()` and translate them with `gettext()`. Then run `make i18n-extract` and translate the new entries in `backend/app/locales/<language>/LC_MESSAGES/messages.po`. |
| Emails | Each email has an English template in `backend/emails/compiled/` and a translation in `backend/emails/compiled/<language>/` with the same `[[placeholders]]`. A missing translation falls back to English. |
| Frontend | Write the English text inside `t("...")` (or `N_("...")` where it is only defined) and add the translation to `frontend/src/locales/<language>.json`. |

The checks fail on any untranslated text: `make i18n-check` for the backend catalogs, a test
for the email templates, and `bun run i18n:check` for the frontend. All three run in CI.

## The interface

The language switcher in the sidebar changes the language of the interface and saves it in the
user's profile, so emails and API errors follow it. Changing the language reloads the page.
After login, the interface adopts the language saved in the profile.
