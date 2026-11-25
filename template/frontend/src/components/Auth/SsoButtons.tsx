// Keelson: single sign-on. One button per OpenID Connect provider configured on the backend
// (OIDC_PROVIDERS); nothing is shown when there is none. The button leaves for the provider's
// sign-in page; the user comes back to /auth/callback, already signed in.
import { useQuery } from "@tanstack/react-query"

import { OauthService } from "@/client"
import { Button } from "@/components/ui/button"
import { N_, t } from "@/i18n"

const API_URL = import.meta.env.VITE_API_URL ?? ""

export function SsoButtons() {
  const { data: providers } = useQuery({
    queryKey: ["oauthProviders"],
    queryFn: async () => (await OauthService.listProviders()).data,
    staleTime: Number.POSITIVE_INFINITY,
  })
  if (!providers?.length) return null
  return (
    <div className="grid gap-2">
      {providers.map((provider) => (
        <Button key={provider.name} variant="outline" asChild>
          <a
            href={`${API_URL}/api/v1/oauth/${encodeURIComponent(provider.name)}/login`}
          >
            {t("Continue with {{provider}}", { provider: provider.label })}
          </a>
        </Button>
      ))}
      <div className="relative text-center text-sm text-muted-foreground">
        {t("or")}
      </div>
    </div>
  )
}

// Reasons a single sign-on did not complete, as the backend reports them (/login?error=).
const SSO_ERRORS: Record<string, string> = {
  failed: N_("Sign-in failed. Please try again."),
  unknown_provider: N_("This sign-in provider is not available."),
  account_disabled: N_("This account is disabled."),
  no_email: N_("The provider did not share your e-mail address."),
  email_unverified: N_("The provider has not verified your e-mail address."),
  domain_not_allowed: N_("Sign-in is not allowed for your e-mail domain."),
  account_exists: N_(
    "An account with this e-mail address already exists. Sign in with your password.",
  ),
}

export const ssoErrorMessage = (code: string): string =>
  t(SSO_ERRORS[code] ?? SSO_ERRORS.failed)
