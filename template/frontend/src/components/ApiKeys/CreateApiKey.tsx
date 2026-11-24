// Keelson: create an API key for the active organization.
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type ApiKeyCreate, ApiKeysService } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import useCustomToast from "@/hooks/useCustomToast"
import { t } from "@/i18n"
import { handleError } from "@/utils"

const formSchema = z.object({
  name: z
    .string()
    .min(1, { message: t("Name is required") })
    .max(100),
  scopes: z
    .array(z.string())
    .min(1, { message: t("Choose at least one scope") }),
  expires_on: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

export const apiKeysQueryKey = ["api-keys"]

const CreateApiKey = ({
  onCreated,
}: {
  onCreated: (token: string) => void
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const { data: scopes } = useQuery({
    queryKey: ["api-key-scopes"],
    queryFn: async () => (await ApiKeysService.listScopes()).data,
  })

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { name: "", scopes: [], expires_on: "" },
  })

  const mutation = useMutation({
    mutationFn: (body: ApiKeyCreate) => ApiKeysService.createApiKey({ body }),
    onSuccess: (response) => {
      form.reset()
      setIsOpen(false)
      onCreated(response.data.token)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: apiKeysQueryKey }),
  })

  const onSubmit = ({ name, scopes: chosen, expires_on }: FormData) => {
    mutation.mutate({
      name,
      scopes: chosen,
      expires_at: expires_on ? new Date(expires_on).toISOString() : null,
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button className="my-4">
          <Plus className="mr-2" />
          {t("New API key")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("New API key")}</DialogTitle>
          <DialogDescription>
            {t("The key acts on the active organization, within its scopes.")}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("Name")}</FormLabel>
                    <FormControl>
                      <Input placeholder={t("CI pipeline")} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="scopes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("Scopes")}</FormLabel>
                    {(scopes ?? []).map((scope) => (
                      <div
                        key={scope.name}
                        className="flex items-center gap-2 text-sm"
                      >
                        <Checkbox
                          id={`scope-${scope.name}`}
                          checked={field.value.includes(scope.name)}
                          onCheckedChange={(checked) =>
                            field.onChange(
                              checked
                                ? [...field.value, scope.name]
                                : field.value.filter((s) => s !== scope.name),
                            )
                          }
                        />
                        <label
                          htmlFor={`scope-${scope.name}`}
                          className="font-mono"
                        >
                          {scope.name}
                        </label>
                        <span className="text-muted-foreground">
                          {scope.description}
                        </span>
                      </div>
                    ))}
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="expires_on"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("Expires on (optional)")}</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  {t("Cancel")}
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                {t("Create")}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateApiKey
