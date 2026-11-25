// Keelstone: choose the organization every request acts on (X-Organization-Id).

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useOrganizations from "@/hooks/useOrganizations"
import { t } from "@/i18n"

export function OrganizationSwitcher() {
  const { organizations, active, switchTo } = useOrganizations()
  if (organizations.length === 0) {
    return null
  }
  return (
    <div className="px-2 group-data-[collapsible=icon]:hidden">
      <Select value={active?.id} onValueChange={switchTo}>
        <SelectTrigger
          className="w-full"
          aria-label={t("Active organization")}
          data-testid="organization-switcher"
        >
          <SelectValue placeholder={t("Organization")} />
        </SelectTrigger>
        <SelectContent>
          {organizations.map((org) => (
            <SelectItem key={org.id} value={org.id}>
              {org.is_personal ? `${org.name} (personal)` : org.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default OrganizationSwitcher
