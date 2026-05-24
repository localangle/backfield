import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { MentionOccurrenceListEditor } from '@/components/MentionOccurrenceListEditor'
import type { PlaceEditFields } from '@/lib/review/entities/location/placeEditFields'
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortPlaceExtractTypeOptions,
} from '@/lib/placeExtractTypeLabel'
import { useMemo } from 'react'

const TYPE_NONE = '__none__'

export interface GeocodedPlaceEditFormProps {
  fields: PlaceEditFields
  onChange: (fields: PlaceEditFields) => void
  disabled?: boolean
  /** When true, omits top border (used inside edit tabs). */
  embeddedInTab?: boolean
  selectedOccurrenceClientId?: string | null
  onSelectOccurrence?: (clientId: string) => void
}

export function GeocodedPlaceEditForm({
  fields,
  onChange,
  disabled = false,
  embeddedInTab = false,
  selectedOccurrenceClientId = null,
  onSelectOccurrence,
}: GeocodedPlaceEditFormProps) {
  const typeOptions = useMemo(() => {
    const base = sortPlaceExtractTypeOptions([...PLACE_EXTRACT_LOCATION_TYPES])
    const current = fields.type.trim()
    if (current && !base.includes(current)) {
      return [current, ...base]
    }
    return base
  }, [fields.type])

  const typeSelectValue = fields.type.trim() ? fields.type.trim() : TYPE_NONE

  return (
    <div
      className={
        embeddedInTab ? 'space-y-3' : 'shrink-0 space-y-3 border-t border-border pt-3'
      }
    >
      {!embeddedInTab ? (
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Place details
        </h4>
      ) : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="place-edit-label">Label</Label>
          <Input
            id="place-edit-label"
            value={fields.label}
            disabled={disabled}
            onChange={(e) => onChange({ ...fields, label: e.target.value })}
            placeholder="Place name"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="place-edit-type">Type</Label>
          <Select
            value={typeSelectValue}
            disabled={disabled}
            onValueChange={(v) =>
              onChange({ ...fields, type: v === TYPE_NONE ? '' : v })
            }
          >
            <SelectTrigger id="place-edit-type" className="h-9 w-full">
              <SelectValue placeholder="Select type…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TYPE_NONE}>None</SelectItem>
              {typeOptions.map((slug) => (
                <SelectItem key={slug} value={slug}>
                  {placeExtractTypeLabel(slug)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="place-edit-address">Formatted address</Label>
          <Input
            id="place-edit-address"
            value={fields.formattedAddress}
            disabled={disabled}
            onChange={(e) => onChange({ ...fields, formattedAddress: e.target.value })}
            placeholder="Geocoded address line"
          />
        </div>
        <MentionOccurrenceListEditor
          occurrences={fields.occurrences}
          disabled={disabled}
          selectedClientId={selectedOccurrenceClientId}
          onSelectOccurrence={onSelectOccurrence}
          onChange={(occurrences) =>
            onChange({
              ...fields,
              occurrences,
              mentionText: occurrences.find((o) => !o.suppressed)?.mentionText.trim() ?? '',
            })
          }
        />
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="place-edit-role">Role in story</Label>
          <Textarea
            id="place-edit-role"
            value={fields.roleInStory}
            disabled={disabled}
            rows={2}
            className="min-h-0 resize-y text-sm"
            onChange={(e) => onChange({ ...fields, roleInStory: e.target.value })}
            placeholder="Why this place matters in the story"
          />
        </div>
      </div>
    </div>
  )
}
