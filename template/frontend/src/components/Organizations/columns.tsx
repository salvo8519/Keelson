import type { ColumnDef } from "@tanstack/react-table"

import type { OrganizationMemberRead } from "@/client"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"
import { N_, t } from "@/i18n"

// Roles of a member in an organization (OrgRole in the backend).
const ROLE_LABELS: Record<string, string> = {
  owner: N_("Owner"),
  admin: N_("Admin"),
  member: N_("Member"),
  viewer: N_("Viewer"),
}

export const memberColumns: ColumnDef<
  DataTableFeatures,
  OrganizationMemberRead
>[] = [
  {
    accessorKey: "full_name",
    header: t("Name"),
    cell: ({ row }) => (
      <span className="font-medium">{row.original.full_name || t("N/A")}</span>
    ),
  },
  {
    accessorKey: "email",
    header: t("Email"),
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.original.email}</span>
    ),
  },
  {
    accessorKey: "role",
    header: t("Role"),
    cell: ({ row }) => (
      <Badge variant={row.original.role === "owner" ? "default" : "secondary"}>
        {t(ROLE_LABELS[row.original.role] ?? row.original.role)}
      </Badge>
    ),
  },
]
