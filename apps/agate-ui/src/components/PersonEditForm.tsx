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
import type { PersonEditFields } from '@/lib/review/entities/person/personEditFields'

export interface PersonEditFormProps {
  fields: PersonEditFields
  onChange: (fields: PersonEditFields) => void
  disabled?: boolean
}

export function PersonEditForm({ fields, onChange, disabled = false }: PersonEditFormProps) {
  const set = (patch: Partial<PersonEditFields>) => onChange({ ...fields, ...patch })

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="person-name">Name</Label>
        <Input
          id="person-name"
          value={fields.name}
          disabled={disabled}
          onChange={(e) => set({ name: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="person-title">Title</Label>
        <Input
          id="person-title"
          value={fields.title}
          disabled={disabled}
          onChange={(e) => set({ title: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="person-affiliation">Affiliation</Label>
        <Input
          id="person-affiliation"
          value={fields.affiliation}
          disabled={disabled}
          onChange={(e) => set({ affiliation: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="person-type">Type</Label>
        <Input
          id="person-type"
          value={fields.personType}
          disabled={disabled}
          onChange={(e) => set({ personType: e.target.value })}
          placeholder="e.g. politician, athlete"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="person-nature">Nature</Label>
        <Select
          value={fields.nature || 'other'}
          disabled={disabled}
          onValueChange={(value) => set({ nature: value })}
        >
          <SelectTrigger id="person-nature">
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
      <div className="space-y-2">
        <Label htmlFor="person-role">Role in story</Label>
        <Input
          id="person-role"
          value={fields.roleInStory}
          disabled={disabled}
          onChange={(e) => set({ roleInStory: e.target.value })}
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="person-public">Public figure</Label>
        <Switch
          id="person-public"
          checked={fields.publicFigure}
          disabled={disabled}
          onCheckedChange={(checked) => set({ publicFigure: checked })}
        />
      </div>
    </div>
  )
}
