import { Building2, Home, KeyRound, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { LanguageSwitcher } from "@/components/Common/LanguageSwitcher"
import { Logo } from "@/components/Common/Logo"
import { OrganizationSwitcher } from "@/components/Organizations/OrganizationSwitcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { t } from "@/i18n"
import { isAdmin } from "@/lib/session"
import { type Item, Main } from "./Main"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: Home, title: t("Dashboard"), path: "/" },
  { icon: Building2, title: t("Organizations"), path: "/organizations" },
  { icon: KeyRound, title: t("API keys"), path: "/api-keys" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = isAdmin(currentUser)
    ? [...baseItems, { icon: Users, title: t("Admin"), path: "/admin" }]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <OrganizationSwitcher />
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <LanguageSwitcher />
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
