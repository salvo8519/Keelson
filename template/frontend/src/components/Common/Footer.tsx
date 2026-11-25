// Keelstone: white label footer (the official template linked to the FastAPI accounts).
import { BRAND_NAME } from "@/brand"

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-4 px-6">
      <p className="text-muted-foreground text-sm">
        {BRAND_NAME} - {currentYear}
      </p>
    </footer>
  )
}
