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
import { Switch } from '@/components/ui/switch'
import { PERSON_NATURE_OPTIONS, personNatureDisplayLabel } from '@/lib/personMentionNature'
import {
  personTypeManualSelectOptions,
  placeExtractTypeLabel,
} from '@/lib/placeExtractTypeLabel'
import type { PersonEditFields } from '@/lib/review/entities/person/personEditFields'
import { cn } from '@/lib/utils'

const PERSON_TYPE_NONE = '__none__'

export interface PersonEditFormProps {
  fields: PersonEditFields
  onChange: (fields: PersonEditFields) => void
  disabled?: boolean
}

export function PersonEditForm({ fields, onChange, disabled = false }: PersonEditFormProps) {
  const set = (patch: Partial<PersonEditFields>) => onChange({ ...fields, ...patch })
  const labelClass = 'text-xs font-medium'
  const inputClass = 'h-8 text-xs'
  const fieldClass = 'min-w-0 space-y-1'
  const typeOptions = useMemo(
    () => personTypeManualSelectOptions(fields.personType),
    [fields.personType],
  )

  return (
    <div className="space-y-3">
      <div className={fieldClass}>
        <Label htmlFor="person-name" className={labelClass}>
          Name
        </Label>
        <Input
          id="person-name"
          className={inputClass}
          value={fields.name}
          disabled={disabled}
          onChange={(e) => set({ name: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className={fieldClass}>
          <Label htmlFor="person-title" className={labelClass}>
            Title
          </Label>
          <Input
            id="person-title"
            className={inputClass}
            value={fields.title}
            disabled={disabled}
            onChange={(e) => set({ title: e.target.value })}
          />
        </div>
        <div className={fieldClass}>
          <Label htmlFor="person-affiliation" className={labelClass}>
            Affiliation
          </Label>
          <Input
            id="person-affiliation"
            className={inputClass}
            value={fields.affiliation}
            disabled={disabled}
            onChange={(e) => set({ affiliation: e.target.value })}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className={fieldClass}>
          <Label htmlFor="person-type" className={labelClass}>
            Type
          </Label>
          <Select
            value={fields.personType || PERSON_TYPE_NONE}
            disabled={disabled}
            onValueChange={(value) =>
              set({ personType: value === PERSON_TYPE_NONE ? '' : value })
            }
          >
            <SelectTrigger id="person-type" className={inputClass}>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PERSON_TYPE_NONE}>None</SelectItem>
              {typeOptions.map((value) => (
                <SelectItem key={value} value={value}>
                  {placeExtractTypeLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className={fieldClass}>
          <Label htmlFor="person-nature" className={labelClass}>
            Nature
          </Label>
          <Select
            value={fields.nature || 'other'}
            disabled={disabled}
            onValueChange={(value) => set({ nature: value })}
          >
            <SelectTrigger id="person-nature" className={inputClass}>
              <SelectValue placeholder="Select nature" />
            </SelectTrigger>
            <SelectContent>
              {PERSON_NATURE_OPTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {personNatureDisplayLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className={fieldClass}>
        <Label htmlFor="person-role" className={labelClass}>
          Role in story
        </Label>
        <Input
          id="person-role"
          className={inputClass}
          value={fields.roleInStory}
          disabled={disabled}
          onChange={(e) => set({ roleInStory: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-2 items-end gap-2">
        <div className="flex items-center gap-2 pb-1">
          <Label htmlFor="person-public" className={cn(labelClass, 'shrink-0')}>
            Public figure
          </Label>
          <Switch
            id="person-public"
            checked={fields.publicFigure}
            disabled={disabled}
            onCheckedChange={(checked) => set({ publicFigure: checked })}
          />
        </div>
        <div className={fieldClass}>
          <Label htmlFor="person-sort-key" className={labelClass}>
            Sort key
          </Label>
          <Input
            id="person-sort-key"
            className={inputClass}
            value={fields.sortKey}
            disabled={disabled}
            onChange={(e) => set({ sortKey: e.target.value })}
            placeholder="Last name"
          />
        </div>
      </div>
    </div>
  )
}
