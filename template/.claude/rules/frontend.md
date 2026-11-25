---
description: Frontend conventions for the React frontend (Vite, TanStack, shadcn/ui)
globs: ["frontend/**/*.ts", "frontend/**/*.tsx", "frontend/**/*.css"]
---

# Frontend Conventions

## Stack

- React 19 and TypeScript (strict), built with Vite into static files served by nginx
- TanStack Router (file routes) and TanStack Query
- Tailwind CSS and shadcn/ui components (`src/components/ui/`)
- Biome for lint and format (`bun run lint`)
- i18next: English source strings, Italian in `src/locales/it.json`

## Structure

- Routes in `src/routes/` (file based); `src/routeTree.gen.ts` is generated: never edit it
- Signed-in pages under `src/routes/_layout/`; public pages (login, sign-up, `/auth/callback`)
  at the root
- Feature components in `src/components/<Feature>/`
- The API client in `src/client/` is generated from `openapi/openapi.json`: never edit it;
  run `make client` after a backend change
- Session tokens and the active organization: `src/lib/session.ts` only

## Conventions

- Call the API through the generated services (`UsersService`, `OauthService`...) with
  TanStack Query; errors through `handleError` and the toast hook
- Every visible string goes through `t("...")`, or `N_("...")` for a string defined before
  translation; add the Italian text to `src/locales/it.json` (`bun run i18n:check` fails
  otherwise)
- The organization of a request is sent by the client in `X-Organization-Id`; do not pass it
  by hand
- No scripts, fonts or images from other origins: the Content Security Policy blocks them
- No icons used as decoration; plain, professional wording
