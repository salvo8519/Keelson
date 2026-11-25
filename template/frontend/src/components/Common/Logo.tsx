// Keelstone: white label. The brand mark (initial on the primary color) and the brand name,
// instead of the FastAPI logo of the official template.
import { Link } from "@tanstack/react-router"

import { BRAND_NAME } from "@/brand"
import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

function Mark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-6 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground",
        className,
      )}
    >
      {BRAND_NAME.charAt(0).toUpperCase()}
    </span>
  )
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const name = <span className="font-semibold">{BRAND_NAME}</span>
  const content =
    variant === "icon" ? (
      <Mark className={className} />
    ) : (
      <span className={cn("inline-flex items-center gap-2", className)}>
        <Mark />
        <span
          className={cn(
            variant === "responsive" && "group-data-[collapsible=icon]:hidden",
          )}
        >
          {name}
        </span>
      </span>
    )

  if (!asLink) {
    return content
  }

  return (
    <Link to="/" aria-label={BRAND_NAME}>
      {content}
    </Link>
  )
}
