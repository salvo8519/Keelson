// Keelson: organizations of the user (tenants) and the members of the active one.
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { MembersService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddOrganization from "@/components/Organizations/AddOrganization"
import { memberColumns } from "@/components/Organizations/columns"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import useOrganizations from "@/hooks/useOrganizations"

export const Route = createFileRoute("/_layout/organizations")({
  component: Organizations,
  head: () => ({
    meta: [{ title: "Organizations" }],
  }),
})

function Members({ organizationId }: { organizationId: string }) {
  const { data } = useQuery({
    queryKey: ["organizations", organizationId, "members"],
    queryFn: async () =>
      (await MembersService.listMembers({ path: { org_id: organizationId } }))
        .data,
  })
  return <DataTable columns={memberColumns} data={data?.items ?? []} />
}

function Organizations() {
  const { organizations, active, switchTo } = useOrganizations()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Organizations</h1>
          <p className="text-muted-foreground">
            Every request acts on the active organization.
          </p>
        </div>
        <AddOrganization />
      </div>

      <ul className="flex flex-col gap-2">
        {organizations.map((org) => (
          <li
            key={org.id}
            className="flex items-center justify-between rounded-md border p-3"
          >
            <div className="flex items-center gap-2">
              <span className="font-medium">{org.name}</span>
              {org.is_personal && <Badge variant="outline">Personal</Badge>}
              <Badge variant="secondary">{org.role}</Badge>
            </div>
            {org.id === active?.id ? (
              <Badge>Active</Badge>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => switchTo(org.id)}
              >
                Make active
              </Button>
            )}
          </li>
        ))}
      </ul>

      {active && (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">Members of {active.name}</h2>
          <Members organizationId={active.id} />
        </section>
      )}
    </div>
  )
}
