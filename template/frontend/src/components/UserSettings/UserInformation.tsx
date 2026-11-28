import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { UsersService, type UserUpdateMe } from "@/client"
import { Button } from "@/components/ui/button"
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
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { t } from "@/i18n"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"
import { IdentityProof } from "./IdentityProof"

const formSchema = z.object({
  full_name: z.string().max(30).optional(),
  email: z.email({ message: t("Invalid email address") }),
  current_password: z.string().max(128).optional(),
})

type FormData = z.infer<typeof formSchema>

const UserInformation = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [editMode, setEditMode] = useState(false)
  const { user: currentUser } = useAuth()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      full_name: currentUser?.full_name ?? undefined,
      email: currentUser?.email,
      current_password: "",
    },
  })
  // A new address needs the current password; an account of single sign-on only has none and
  // needs a sign-in within the last 5 minutes instead.
  const emailChanged = form.watch("email") !== currentUser?.email
  const hasPassword = currentUser?.has_password ?? true

  const toggleEditMode = () => {
    setEditMode(!editMode)
  }

  // The profile fields change at once; a new email address only once the link sent to it is
  // followed (/confirm-email), so the form shows the address in force until then.
  const mutation = useMutation({
    mutationFn: async ({
      profile,
      email,
      currentPassword,
    }: {
      profile: UserUpdateMe
      email?: string
      currentPassword?: string
    }) => {
      if (Object.keys(profile).length > 0) {
        await UsersService.updateCurrentUser({ body: profile })
      }
      if (email) {
        await UsersService.requestEmailChange({
          body: { email, current_password: currentPassword || null },
        })
      }
      return { emailRequested: !!email }
    },
    onSuccess: ({ emailRequested }) => {
      showSuccessToast(
        emailRequested
          ? t("Check the new address for a confirmation link")
          : t("User updated successfully"),
      )
      form.reset({
        ...form.getValues(),
        email: currentUser?.email,
        current_password: "",
      })
      toggleEditMode()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      form.resetField("current_password")
      queryClient.invalidateQueries()
    },
  })

  const onSubmit = (data: FormData) => {
    const profile: UserUpdateMe = {}

    // only include fields that have changed
    if (data.full_name !== currentUser?.full_name) {
      profile.full_name = data.full_name
    }
    const email = data.email !== currentUser?.email ? data.email : undefined

    mutation.mutate({
      profile,
      email,
      currentPassword: email ? data.current_password : undefined,
    })
  }

  const onCancel = () => {
    form.reset()
    toggleEditMode()
  }

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">{t("User Information")}</h3>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-4"
        >
          <FormField
            control={form.control}
            name="full_name"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>{t("Full name")}</FormLabel>
                  <FormControl>
                    <Input type="text" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>{t("Full name")}</FormLabel>
                  <p
                    className={cn(
                      "py-2 truncate max-w-sm",
                      !field.value && "text-muted-foreground",
                    )}
                  >
                    {field.value || "N/A"}
                  </p>
                </FormItem>
              )
            }
          />

          <FormField
            control={form.control}
            name="email"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>{t("Email")}</FormLabel>
                  <FormControl>
                    <Input type="email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>{t("Email")}</FormLabel>
                  <p className="py-2 truncate max-w-sm">{field.value}</p>
                </FormItem>
              )
            }
          />

          {editMode && emailChanged && (
            <IdentityProof
              control={form.control}
              name="current_password"
              hasPassword={hasPassword}
              description={t("Required to change the email address.")}
              signInAgainHint={t(
                "Your account signs in through single sign-on: if you signed in more than 5 minutes ago, sign out and sign in again before changing the email address.",
              )}
              testId="email-current-password-input"
            />
          )}

          <div className="flex gap-3">
            {editMode ? (
              <>
                <LoadingButton
                  type="submit"
                  loading={mutation.isPending}
                  disabled={!form.formState.isDirty}
                >
                  {t("Save")}
                </LoadingButton>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onCancel}
                  disabled={mutation.isPending}
                >
                  {t("Cancel")}
                </Button>
              </>
            ) : (
              <Button type="button" onClick={toggleEditMode}>
                {t("Edit")}
              </Button>
            )}
          </div>
        </form>
      </Form>
    </div>
  )
}

export default UserInformation
