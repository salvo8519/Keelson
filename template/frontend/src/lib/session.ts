import type { UserRead } from "@/client"

// Keelson: the signed-in session in the browser. The access and refresh tokens are HttpOnly
// cookies set by the API: no script in the page can read them, so an injected script cannot
// steal them. This module keeps only what is not secret: whether the user signed in (to route
// without a request) and the active organization.
const SIGNED_IN = "signed_in"
const ACTIVE_ORGANIZATION = "active_organization_id"
const STALE_TOKENS = ["access_token", "refresh_token"]

export const session = {
  isSignedIn: () => localStorage.getItem(SIGNED_IN) === "1",
  markSignedIn: () => {
    localStorage.setItem(SIGNED_IN, "1")
    // Tokens stored by an earlier version are removed for good.
    for (const key of STALE_TOKENS) localStorage.removeItem(key)
  },
  signOut: () => {
    localStorage.removeItem(SIGNED_IN)
    localStorage.removeItem(ACTIVE_ORGANIZATION)
    for (const key of STALE_TOKENS) localStorage.removeItem(key)
  },
  activeOrganization: () => localStorage.getItem(ACTIVE_ORGANIZATION),
  setActiveOrganization: (organizationId: string) =>
    localStorage.setItem(ACTIVE_ORGANIZATION, organizationId),
}

// The backend header that selects the active organization of a request.
export const ORGANIZATION_HEADER = "X-Organization-Id"

export const isAdmin = (user?: UserRead | null) => user?.role === "admin"
