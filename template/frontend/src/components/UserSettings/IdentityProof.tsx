import { useEffect } from "react"
import {
  type Control,
  type FieldPath,
  type FieldValues,
  useFormContext,
} from "react-hook-form"

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { PasswordInput } from "@/components/ui/password-input"
import { t } from "@/i18n"

interface IdentityProofProps<T extends FieldValues> {
  control: Control<T>
  /** The form field that holds the current password. */
  name: FieldPath<T>
  /** From GET /users/me: accounts of single sign-on only have no password. */
  hasPassword: boolean
  /** Why the password is asked for, shown under the field. */
  description: string
  /** What an account without a password does instead: sign in again. */
  signInAgainHint: string
  testId: string
}

// Keelstone: a sensitive change of the caller's own account (address, deletion) asks them to
// prove their identity again. With the current password when the account has one; an account
// of single sign-on only needs a sign-in within the last 5 minutes, which this explains.
// The typed password is cleared when the field goes away (a dialog closed, an edit cancelled),
// so it does not stay in the form state and reappear later.
export function IdentityProof<T extends FieldValues>({
  control,
  name,
  hasPassword,
  description,
  signInAgainHint,
  testId,
}: IdentityProofProps<T>) {
  const { resetField } = useFormContext<T>()
  useEffect(() => () => resetField(name), [resetField, name])

  if (!hasPassword) {
    return <p className="text-sm text-muted-foreground">{signInAgainHint}</p>
  }
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("Current Password")}</FormLabel>
          <FormControl>
            <PasswordInput
              data-testid={testId}
              autoComplete="current-password"
              {...field}
            />
          </FormControl>
          <FormDescription>{description}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}
