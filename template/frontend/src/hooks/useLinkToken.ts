import { useEffect, useState } from "react"

// Keelstone: the token of a link sent by e-mail (password reset, address confirmation). The API
// puts it in the fragment (#token=...), which the browser never sends to a server, so it stays
// out of the access log of the web server and out of any Referer. Links sent before that carried
// it in the query string (?token=...), which is still read. Either way the token is removed from
// the address bar and the history as soon as the page has it.
const TOKEN = "token"

function readLinkToken(): string {
  const fromFragment = new URLSearchParams(window.location.hash.slice(1)).get(
    TOKEN,
  )
  return (
    fromFragment ?? new URLSearchParams(window.location.search).get(TOKEN) ?? ""
  )
}

function stripLinkToken(): void {
  const url = new URL(window.location.href)
  url.hash = ""
  url.searchParams.delete(TOKEN)
  window.history.replaceState(
    window.history.state,
    "",
    url.pathname + url.search,
  )
}

/** The token of the link that opened the page, read once; "" when there is none. */
export function useLinkToken(): string {
  const [token] = useState(readLinkToken)
  useEffect(() => {
    if (token) stripLinkToken()
  }, [token])
  return token
}
