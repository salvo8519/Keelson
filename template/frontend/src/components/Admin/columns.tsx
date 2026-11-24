import type { ColumnDef } from "@tanstack/react-table"

import type { UserRead } from "@/client"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"
import { t } from "@/i18n"
import { isAdmin } from "@/lib/session"
import { cn } from "@/lib/utils"
import { UserActionsMenu } from "./UserActionsMenu"

export type UserTableData = UserRead & {
  isCurrentUser: boolean
}

export const columns: ColumnDef<DataTableFeatures, UserTableData>[] = [
  {
    accessorKey: "full_name",
    header: t("Full Name"),
    cell: ({ row }) => {
      const fullName = row.original.full_name
      return (
        <div className="flex items-center gap-2">
          <span
            className={cn("font-medium", !fullName && "text-muted-foreground")}
          >
            {fullName || t("N/A")}
          </span>
          {row.original.isCurrentUser && (
            <Badge variant="outline" className="text-xs">
              {t("You")}
            </Badge>
          )}
        </div>
      )
    },
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
      <Badge variant={isAdmin(row.original) ? "default" : "secondary"}>
        {isAdmin(row.original) ? t("Administrator") : t("User")}
      </Badge>
    ),
  },
  {
    accessorKey: "is_active",
    header: t("Status"),
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "size-2 rounded-full",
            row.original.is_active ? "bg-green-500" : "bg-gray-400",
          )}
        />
        <span className={row.original.is_active ? "" : "text-muted-foreground"}>
          {row.original.is_active ? t("Active") : t("Inactive")}
        </span>
      </div>
    ),
  },
  {
    id: "actions",
    header: () => <span className="sr-only">{t("Actions")}</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <UserActionsMenu user={row.original} />
      </div>
    ),
  },
]
