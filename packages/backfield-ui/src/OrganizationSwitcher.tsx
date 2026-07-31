import { useId, useState } from "react"

export interface OrganizationSwitcherOption {
  id: number
  name: string
  slug: string
}

export interface OrganizationSwitcherProps {
  organizations: OrganizationSwitcherOption[]
  organizationId: number | null
  onSwitch: (organizationId: number) => Promise<void>
}

export function OrganizationSwitcher({
  organizations,
  organizationId,
  onSwitch,
}: OrganizationSwitcherProps) {
  const id = useId()
  const [switching, setSwitching] = useState(false)
  const [error, setError] = useState("")
  if (organizations.length < 2 || organizationId == null) return null

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="sr-only">
        Organization
      </label>
      <select
        id={id}
        aria-label="Organization"
        value={organizationId}
        disabled={switching}
        className="h-9 max-w-56 rounded-md border border-border bg-background px-2 text-sm"
        onChange={(event) => {
          const nextId = Number(event.target.value)
          if (nextId === organizationId) return
          setSwitching(true)
          setError("")
          void onSwitch(nextId)
            .catch(() => setError("Could not switch organizations. Please try again."))
            .finally(() => setSwitching(false))
        }}
      >
        {organizations.map((organization) => (
          <option key={organization.id} value={organization.id}>
            {organization.name}
          </option>
        ))}
      </select>
      {error ? (
        <span role="alert" className="text-sm text-destructive">
          {error}
        </span>
      ) : null}
    </div>
  )
}
