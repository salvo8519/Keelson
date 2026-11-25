// Keelstone: translation of the interface with i18next.
//
// The English text is the key: t("Save") returns "Save" in English and the translation from
// src/locales/<language>.json in other languages. `bun run i18n:check` fails when a key used in
// the code has no translation. Changing the language reloads the page, so module-level texts
// (form validation messages, navigation) are translated too.
// Every module that calls t() imports this one, so i18next is initialised before any text is
// read: import order does not matter.
import i18next from "i18next"

import { LANGUAGES, type LanguageCode } from "./locales/languages"

const STORAGE_KEY = "language"
const SOURCE_LANGUAGE: LanguageCode = "en"

const catalogs = import.meta.glob<Record<string, string>>("./locales/*.json", {
  eager: true,
  import: "default",
})

const resources = Object.fromEntries(
  LANGUAGES.map(({ code }) => [
    code,
    { translation: catalogs[`./locales/${code}.json`] ?? {} },
  ]),
)

const isSupported = (code: string | null | undefined): code is LanguageCode =>
  !!code && LANGUAGES.some((language) => language.code === code)

function initialLanguage(): LanguageCode {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (isSupported(stored)) return stored
  const browser = navigator.language?.split("-")[0]
  return isSupported(browser) ? browser : SOURCE_LANGUAGE
}

i18next.init({
  resources,
  lng: initialLanguage(),
  fallbackLng: SOURCE_LANGUAGE,
  keySeparator: false,
  nsSeparator: false,
  returnEmptyString: false,
  interpolation: { escapeValue: false },
  initAsync: false,
})

export const t = (key: string, options?: Record<string, unknown>): string =>
  i18next.t(key, options)

// Marks a text for translation where it is defined, without translating it; t() translates it
// where it is shown. Same convention as N_ in the backend.
export const N_ = (key: string): string => key

export const currentLanguage = (): LanguageCode =>
  i18next.language as LanguageCode

export function setLanguage(code: string, { reload = true } = {}) {
  if (!isSupported(code) || code === currentLanguage()) return
  localStorage.setItem(STORAGE_KEY, code)
  if (reload) window.location.reload()
}

export { isSupported, LANGUAGES }
