import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"

import { UsersService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { t } from "@/i18n"
import { handleError } from "@/utils"
import { IdentityProof } from "./IdentityProof"

type FormData = { current_password: string }

const DeleteConfirmation = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const form = useForm<FormData>({ defaultValues: { current_password: "" } })
  const { user: currentUser, logout } = useAuth()
  // Deleting the account proves the identity again: the current password, or for an account of
  // single sign-on only a sign-in within the last 5 minutes.
  const hasPassword = currentUser?.has_password ?? true

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      UsersService.deleteCurrentUser({
        body: { current_password: hasPassword ? data.current_password : null },
      }),
    onSuccess: () => {
      showSuccessToast(t("Your account has been successfully deleted"))
      logout()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      // The password is asked again for every attempt, never kept in the form.
      form.resetField("current_password")
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="destructive" className="mt-3">
          {t("Delete Account")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>{t("Confirmation Required")}</DialogTitle>
              <DialogDescription>
                {t(
                  "All your account data will be permanently deleted. This action cannot be undone.",
                )}
              </DialogDescription>
            </DialogHeader>

            <div className="mt-4">
              <IdentityProof
                control={form.control}
                name="current_password"
                hasPassword={hasPassword}
                description={t("Required to delete the account.")}
                signInAgainHint={t(
                  "Your account signs in through single sign-on: if you signed in more than 5 minutes ago, sign out and sign in again before deleting the account.",
                )}
                testId="delete-current-password-input"
              />
            </div>

            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  {t("Cancel")}
                </Button>
              </DialogClose>
              <LoadingButton
                variant="destructive"
                type="submit"
                loading={mutation.isPending}
              >
                {t("Delete")}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default DeleteConfirmation
