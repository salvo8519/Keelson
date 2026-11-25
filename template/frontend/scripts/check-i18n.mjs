// Keelstone: every key used with t("...") or N_("...") in src/ has a translation in each catalog of
// src/locales (English, the source language, needs none). Run: bun run i18n:check
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

const SRC = new URL("../src/", import.meta.url).pathname
const LOCALES = join(SRC, "locales")
const KEY = /\b(?:t|N_)\(\s*"((?:[^"\\]|\\.)*)"/g

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory())
      return name === "client" ? [] : files(path)
    return /\.(tsx?|jsx?)$/.test(name) ? [path] : []
  })
}

const keys = new Set()
for (const file of files(SRC)) {
  for (const match of readFileSync(file, "utf8").matchAll(KEY)) {
    keys.add(JSON.parse(`"${match[1]}"`))
  }
}

let failed = false
for (const name of readdirSync(LOCALES).filter((n) => n.endsWith(".json"))) {
  const catalog = JSON.parse(readFileSync(join(LOCALES, name), "utf8"))
  const missing = [...keys].filter((key) => !catalog[key]).sort()
  const unused = Object.keys(catalog)
    .filter((key) => !keys.has(key))
    .sort()
  if (missing.length) {
    failed = true
    console.error(`${name}: ${missing.length} untranslated`)
    for (const key of missing) console.error(`  ${key}`)
  }
  if (unused.length) {
    console.warn(`${name}: ${unused.length} unused (remove them)`)
    for (const key of unused) console.warn(`  ${key}`)
  }
}
console.log(`${keys.size} keys checked`)
process.exit(failed ? 1 : 0)
