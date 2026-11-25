import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { z } from "zod"
import { BRAND_NAME } from "@/brand"
import { AuthService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { t } from "@/i18n"
import { handleError } from "@/utils"

// Keelstone: the page of the link sent to a new email address. The address changes only when
// the user confirms here; the request is a deliberate click, not a page load, so a mail scanner
// that opens the link changes nothing.
const searchSchema = z.object({
  token: z.string().catch(""),
})

export const Route = createFileRoute("/confirm-email")({
  component: ConfirmEmail,
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.token) {
      throw redirect({ to: "/login" })
    }
  },
  head: () => ({
    meta: [
      {
        title: `${t("Confirm email address")} - ${BRAND_NAME}`,
      },
    ],
  }),
})

function ConfirmEmail() {
  const { token } = Route.useSearch()
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
