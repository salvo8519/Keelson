import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { client } from "./client/client.gen"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import { currentLanguage } from "./i18n"
import { ORGANIZATION_HEADER, session } from "./lib/session"
import "./index.css"
import "./brand.css"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  auth: () => session.accessToken() || "",
})

// Keelson: every request carries the active organization (the backend checks the membership)
// and the language of the interface (used when the user has no saved preference).
client.instance.interceptors.request.use((config) => {
  const organizationId = session.activeOrganization()
  if (organizationId) {
    config.headers.set(ORGANIZATION_HEADER, organizationId)
  }
  config.headers.set("Accept-Language", currentLanguage())
  return config
})

// Keelson: only 401 ends the session. A 403 is a missing role or scope in the active
// organization (upstream signed the user out on 403 too).
const handleApiError = (error: Error) => {
  if (error instanceof AxiosError && error.response?.status === 401) {
    session.signOut()
    window.location.href = "/login"
  }
}
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

document.documentElement.lang = currentLanguage()

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
