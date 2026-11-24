// Keelson: the signed-in session in the browser. One place for the storage keys, so the API
// client, the auth hook and the organization switcher agree.
import type { UserRead } from "@/client"

const ACCESS_TOKEN = "access_token"
const REFRESH_TOKEN = "refresh_token"
const ACTIVE_ORGANIZATION = "active_organization_id"

export const session = {
  accessToken: () => localStorage.getItem(ACCESS_TOKEN),
  signIn: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_TOKEN, accessToken)
    localStorage.setItem(REFRESH_TOKEN, refreshToken)
  },
  signOut: () => {
    localStorage.removeItem(ACCESS_TOKEN)
    localStorage.removeItem(REFRESH_TOKEN)
    localStorage.removeItem(ACTIVE_ORGANIZATION)
  },
  activeOrganization: () => localStorage.getItem(ACTIVE_ORGANIZATION),
  setActiveOrganization: (organizationId: string) =>
    localStorage.setItem(ACTIVE_ORGANIZATION, organizationId),
}

// The backend header that selects the active organization of a request.
export const ORGANIZATION_HEADER = "X-Organization-Id"

export const isAdmin = (user?: UserRead | null) => user?.role === "admin"
