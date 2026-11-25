// Keelstone: API keys of the active organization (owners and administrators).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import { type ApiKeyRead, ApiKeysService } from "@/client"
import CreateApiKey, {
  apiKeysQueryKey,
} from "@/components/ApiKeys/CreateApiKey"
import ShowToken from "@/components/ApiKeys/ShowToken"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import useCustomToast from "@/hooks/useCustomToast"
import { N_, t } from "@/i18n"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/api-keys")({
  component: ApiKeys,
  head: () => ({ meta: [{ title: t("API keys") }] }),
})

const formatDate = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : "-"

function status(key: ApiKeyRead) {
  const now = Date.now()
  if (key.revoked_at && new Date(key.revoked_at).getTime() <= now)
    return N_("Revoked")
  if (key.expires_at && new Date(key.expires_at).getTime() <= now)
    return N_("Expired")
  if (key.revoked_at) return N_("Rotating")
  return N_("Active")
}

function ApiKeys() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [token, setToken] = useState<string | null>(null)
  const { data: keys, error } = useQuery({
    queryKey: apiKeysQueryKey,
    queryFn: async () => (await ApiKeysService.listApiKeys()).data,
  })
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: apiKeysQueryKey })

  const rotate = useMutation({
    mutationFn: (keyId: string) =>
      ApiKeysService.rotateApiKey({
        path: { key_id: keyId },
        body: { grace_minutes: 60 },
      }),
    onSuccess: (response) => setToken(response.data.token),
    onError: handleError.bind(showErrorToast),
    onSettled: refresh,
  })
  const revoke = useMutation({
    mutationFn: (keyId: string) =>
      ApiKeysService.revokeApiKey({ path: { key_id: keyId } }),
    onSuccess: () => showSuccessToast(t("API key revoked")),
    onError: handleError.bind(showErrorToast),
    onSettled: refresh,
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("API keys")}</h1>
          <p className="text-muted-foreground">
            {t("Keys let other systems act on the active organization.")}
          </p>
        </div>
        <CreateApiKey onCreated={setToken} />
      </div>
      {error ? (
        <p className="text-muted-foreground">
          {t(
            "Only owners and administrators of the organization manage its keys.",
          )}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("Name")}</TableHead>
              <TableHead>{t("Key")}</TableHead>
              <TableHead>{t("Scopes")}</TableHead>
              <TableHead>{t("Last used")}</TableHead>
              <TableHead>{t("Expires")}</TableHead>
              <TableHead>{t("Status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(keys ?? []).map((key) => {
              const state = status(key)
              return (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell className="font-mono">{key.prefix}</TableCell>
                  <TableCell>{key.scopes.join(", ")}</TableCell>
                  <TableCell>{formatDate(key.last_used_at)}</TableCell>
                  <TableCell>{formatDate(key.expires_at)}</TableCell>
                  <TableCell>
                    <Badge
                      variant={state === "Active" ? "default" : "secondary"}
                    >
                      {t(state)}
                    </Badge>
                  </TableCell>
                  <TableCell className="flex gap-2">
                    {state === "Active" && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => rotate.mutate(key.id)}
                        >
                          {t("Rotate")}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => revoke.mutate(key.id)}
                        >
                          {t("Revoke")}
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
      <ShowToken token={token} onClose={() => setToken(null)} />
    </div>
  )
}
