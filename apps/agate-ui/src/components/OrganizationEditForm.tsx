import { useMemo } from 'react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ORGANIZATION_NATURE_OPTIONS, organizationNatureDisplayLabel } from '@/lib/organizationMentionNature'
import {
  organizationTypeManualSelectOptions,
  placeExtractTypeLabel,
} from '@/lib/placeExtractTypeLabel'
import type { OrganizationEditFields } from '@/lib/review/entities/organization/organizationEditFields'
import { cn } from '@/lib/utils'

const ORGANIZATION_TYPE_NONE = '__none__'

export interface OrganizationEditFormProps {
  fields: OrganizationEditFields
  onChange: (fields: OrganizationEditFields) => void
  disabled?: boolean
}

export function OrganizationEditForm({
  fields,
  onChange,
  disabled = false,
}: OrganizationEditFormProps) {
  const set = (patch: Partial<OrganizationEditFields>) => onChange({ ...fields, ...patch })
  const labelClass = 'text-xs font-medium'
  const inputClass = 'h-8 text-xs'
  const fieldClass = 'min-w-0 space-y-1'
  const typeOptions = useMemo(
    () => organizationTypeManualSelectOptions(fields.organizationType),
    [fields.organizationType],
  )

  return (
    <div className="space-y-3">
      <div className={fieldClass}>
        <Label htmlFor="organization-name" className={labelClass}>
          Name
        </Label>
        <Input
          id="organization-name"
          className={inputClass}
          value={fields.name}
          disabled={disabled}
          onChange={(e) => set({ name: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className={fieldClass}>
          <Label htmlFor="organization-type" className={labelClass}>
            Type
          </Label>
          <Select
            value={fields.organizationType || ORGANIZATION_TYPE_NONE}
            disabled={disabled}
            onValueChange={(value) =>
              set({ organizationType: value === ORGANIZATION_TYPE_NONE ? '' : value })
            }
          >
            <SelectTrigger id="organization-type" className={inputClass}>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ORGANIZATION_TYPE_NONE}>None</SelectItem>
              {typeOptions.map((value) => (
                <SelectItem key={value} value={value}>
                  {placeExtractTypeLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className={fieldClass}>
          <Label htmlFor="organization-nature" className={labelClass}>
            Nature
          </Label>
          <Select
            value={fields.nature || 'other'}
            disabled={disabled}
            onValueChange={(value) => set({ nature: value })}
          >
            <SelectTrigger id="organization-nature" className={inputClass}>
              <SelectValue placeholder="Select nature" />
            </SelectTrigger>
            <SelectContent>
              {ORGANIZATION_NATURE_OPTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {organizationNatureDisplayLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className={fieldClass}>
        <Label htmlFor="organization-role" className={labelClass}>
          Role in story
        </Label>
        <Input
          id="organization-role"
          className={inputClass}
          value={fields.roleInStory}
          disabled={disabled}
          onChange={(e) => set({ roleInStory: e.target.value })}
        />
      </div>
    </div>
  )
}
