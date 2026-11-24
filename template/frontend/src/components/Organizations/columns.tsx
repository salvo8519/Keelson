import type { ColumnDef } from "@tanstack/react-table"

import type { OrganizationMemberRead } from "@/client"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"

export const memberColumns: ColumnDef<
  DataTableFeatures,
  OrganizationMemberRead
>[] = [
  {
    accessorKey: "full_name",
    header: "Name",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.full_name || "N/A"}</span>
    ),
  },
  {
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.original.email}</span>
    ),
  },
  {
    accessorKey: "role",
    header: "Role",
    cell: ({ row }) => (
      <Badge variant={row.original.role === "owner" ? "default" : "secondary"}>
        {row.original.role}
      </Badge>
    ),
  },
]
