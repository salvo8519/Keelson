// Keelstone: the organizations of the signed-in user and the active one.
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { type OrganizationRead, OrganizationsService } from "@/client"
import { session } from "@/lib/session"

export const organizationsQueryKey = ["organizations"]

const useOrganizations = () => {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: organizationsQueryKey,
    queryFn: async () => (await OrganizationsService.listOrganizations()).data,
  })
  const organizations: OrganizationRead[] = data?.items ?? []
  const storedId = session.activeOrganization()
  // Without a stored choice the backend uses the personal organization; show the same.
  const active =
    organizations.find((org) => org.id === storedId) ??
    organizations.find((org) => org.is_personal) ??
    organizations[0]

  const switchTo = (organizationId: string) => {
    session.setActiveOrganization(organizationId)
    // Every cached answer belonged to the previous organization.
    queryClient.invalidateQueries()
  }

  return { organizations, active, switchTo, isLoading }
}

export default useOrganizations
