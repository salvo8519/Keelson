// Keelson: back from a single sign-on provider. The backend sent a one-time code (never the
// tokens, which would stay in the browser history); it is exchanged here for the session,
// which the API sets as HttpOnly cookies.
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef } from "react"
import { z } from "zod"

import { OauthService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { completeSignIn } from "@/hooks/useAuth"
import { t } from "@/i18n"

export const Route = createFileRoute("/auth/callback")({
  component: SsoCallback,
  validateSearch: z.object({ code: z.string().optional() }),
})

function SsoCallback() {
  const { code } = Route.useSearch()
  const navigate = useNavigate()
  const started = useRef(false)

  useEffect(() => {
    // The code is valid once: exchange it once, even if the effect runs twice.
    if (started.current) return
    started.current = true
    const failed = () => navigate({ to: "/login", search: { error: "failed" } })
    if (!code) {
      failed()
      return
    }
    OauthService.exchangeCode({ body: { code } })
      .then(() => completeSignIn())
      .then((languageChanged) => {
        // Remove the code from the address bar and the history.
        window.history.replaceState(null, "", "/")
        if (languageChanged) window.location.assign("/")
        else navigate({ to: "/" })
      })
      .catch(failed)
  }, [code, navigate])

  return (
    <AuthLayout>
      <p className="text-center text-sm text-muted-foreground">
        {t("Signing you in...")}
      </p>
    </AuthLayout>
  )
}
