import { createFileRoute } from "@tanstack/react-router"
import { BRAND_NAME } from "@/brand"
import useAuth from "@/hooks/useAuth"
import { t } from "@/i18n"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: `${t("Dashboard")} - ${BRAND_NAME}`,
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()

  return (
    <div>
      <div>
        <h1 className="text-2xl truncate max-w-sm">
          {t("Hello, {{name}}", {
            name: currentUser?.full_name || currentUser?.email,
          })}
        </h1>
        <p className="text-muted-foreground">{t("Welcome back.")}</p>
      </div>
    </div>
  )
}
