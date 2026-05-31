import type { ReactNode } from "react"
import { Breadcrumbs, type BreadcrumbItem } from "@/components/Breadcrumbs"

/** Shared layout + field styling for Stylebook manual canonical create pages. */
export const createCanonicalFormClasses = {
  grid: "grid grid-cols-12 gap-6",
  primaryColumn: "col-span-6",
  /** Single-card create pages (no side panel). */
  wideFormColumn: "col-span-12",
  cardContent: "space-y-4",
  fieldGrid: "grid grid-cols-1 md:grid-cols-2 gap-4",
  fieldGridFull: "md:col-span-2",
  selectTrigger: "h-10 w-full",
  footer: "mt-6 flex justify-end gap-2",
} as const

type CreateCanonicalShellProps = {
  breadcrumbs: BreadcrumbItem[]
  title: string
  children: ReactNode
  footer: ReactNode
}

export function CreateCanonicalShell({
  breadcrumbs,
  title,
  children,
  footer,
}: CreateCanonicalShellProps) {
  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <Breadcrumbs className="mb-3" items={breadcrumbs} />
        <h1 className="text-3xl font-bold">{title}</h1>
      </div>
      {children}
      <div className={createCanonicalFormClasses.footer}>{footer}</div>
    </div>
  )
}
