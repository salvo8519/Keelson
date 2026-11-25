import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  createFileRoute,
  Navigate,
  Link as RouterLink,
} from "@tanstack/react-router"
import { BRAND_NAME } from "@/brand"
import { AuthService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { useLinkToken } from "@/hooks/useLinkToken"
import { t } from "@/i18n"
import { handleError } from "@/utils"

// Keelstone: the page of the link sent to a new email address. The address changes only when
// the user confirms here; the request is a deliberate click, not a page load, so a mail scanner
// that opens the link changes nothing. The token is read from the link and then removed from
// the address bar (useLinkToken).
export const Route = createFileRoute("/confirm-email")({
  component: ConfirmEmail,
  head: () => ({
    meta: [
      {
        title: `${t("Confirm email address")} - ${BRAND_NAME}`,
      },
    ],
  }),
})

function ConfirmEmail() {
  const token = useLinkToken()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: () => AuthService.confirmEmailChange({ body: { token } }),
    onSuccess: () => {
      showSuccessToast(t("Email address confirmed"))
      queryClient.invalidateQueries()
    },
    onError: handleError.bind(showErrorToast),
  })

  if (!token) return <Navigate to="/login" />

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-2xl font-bold">{t("Confirm email address")}</h1>
          <p className="text-sm text-muted-foreground">
            {mutation.isSuccess
              ? t("Your account now uses this email address.")
              : t("Confirm to make this the email address of your account.")}
          </p>
        </div>
        {!mutation.isSuccess && (
          <LoadingButton
            type="button"
            className="w-full"
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {t("Confirm email address")}
          </LoadingButton>
        )}
        <div className="text-center text-sm">
          <RouterLink to="/" className="underline underline-offset-4">
            {t("Continue")}
          </RouterLink>
        </div>
      </div>
    </AuthLayout>
  )
}
