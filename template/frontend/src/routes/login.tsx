import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { BRAND_NAME } from "@/brand"
import type { Body_auth_login as AccessToken } from "@/client"
import { SsoButtons, ssoErrorMessage } from "@/components/Auth/SsoButtons"
import { AuthLayout } from "@/components/Common/AuthLayout"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { t } from "@/i18n"

const formSchema = z.object({
  username: z.email({ message: t("Invalid email address") }),
  password: z
    .string()
    .min(1, { message: t("Password is required") })
    .min(8, { message: t("Password must be at least 8 characters") }),
}) satisfies z.ZodType<AccessToken>

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  // Keelstone: a single sign-on that did not complete comes back with the reason.
  validateSearch: z.object({ error: z.string().optional() }),
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: `${t("Log In")} - ${BRAND_NAME}`,
      },
    ],
  }),
})

function Login() {
  const { loginMutation } = useAuth()
  const { error } = Route.useSearch()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      username: "",
      password: "",
    },
  })

  const onSubmit = (data: FormData) => {
    if (loginMutation.isPending) return
    loginMutation.mutate(data)
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">{t("Login to your account")}</h1>
          </div>

          {error && (
            <p role="alert" className="text-center text-sm text-destructive">
              {ssoErrorMessage(error)}
            </p>
          )}

          <SsoButtons />

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("Email")}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="email-input"
                      placeholder="user@example.com"
                      type="email"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center">
                    <FormLabel>{t("Password")}</FormLabel>
                    <RouterLink
                      to="/recover-password"
                      className="ml-auto text-sm underline-offset-4 hover:underline"
                    >
                      {t("Forgot your password?")}
                    </RouterLink>
                  </div>
                  <FormControl>
                    <PasswordInput
                      data-testid="password-input"
                      placeholder={t("Password")}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <LoadingButton type="submit" loading={loginMutation.isPending}>
              {t("Log In")}
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            {t("Don't have an account yet?")}{" "}
            <RouterLink to="/signup" className="underline underline-offset-4">
              {t("Sign up")}
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
