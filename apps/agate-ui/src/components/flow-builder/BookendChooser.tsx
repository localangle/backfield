import { nodeMetadata } from '@/nodes/registry'
import { getNodeBgColor, getNodeIcon } from '@/lib/nodeUtils'
import { cn } from '@/lib/utils'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { INPUT_BOOKEND_TYPES, OUTPUT_BOOKEND_TYPES } from '@/lib/flowValidation'

const INPUT_CARD_COPY: Record<string, { title: string; description: string }> = {
  TextInput: {
    title: 'Paste or type text',
    description: 'Add article text directly in the flow — ideal for trying a single story.',
  },
  JSONInput: {
    title: 'Structured JSON',
    description: 'Provide article fields as JSON when your content already lives in a structured format.',
  },
  S3Input: {
    title: 'Files in Amazon S3',
    description: 'Read articles from JSON files stored in a cloud storage bucket.',
  },
}

const OUTPUT_CARD_COPY: Record<string, { title: string; description: string }> = {
  Output: {
    title: 'JSON results',
    description: 'Collect the flow results as a single JSON file for review or export.',
  },
  DBOutput: {
    title: 'Stylebook',
    description: 'Save places and related results to your organization Stylebook.',
  },
}

type BookendChooserProps = {
  kind: 'input' | 'output'
  selectedType?: string
  onSelect: (type: string) => void
}

export default function BookendChooser({ kind, selectedType, onSelect }: BookendChooserProps) {
  const allowedTypes = kind === 'input' ? INPUT_BOOKEND_TYPES : OUTPUT_BOOKEND_TYPES
  const copyMap = kind === 'input' ? INPUT_CARD_COPY : OUTPUT_CARD_COPY
  const options = nodeMetadata.filter((meta) =>
    (allowedTypes as readonly string[]).includes(meta.type),
  )

  return (
    <div className="mx-auto grid max-w-4xl gap-4 md:grid-cols-2 lg:grid-cols-3">
      {options.map((meta) => {
        const copy = copyMap[meta.type] ?? {
          title: meta.label,
          description: meta.description,
        }
        const isSelected = selectedType === meta.type
        const icon = getNodeIcon(meta.type, 'h-5 w-5')
        const bgColor = getNodeBgColor(meta.type)

        return (
          <button
            key={meta.type}
            type="button"
            onClick={() => onSelect(meta.type)}
            className="text-left"
          >
            <Card
              className={cn(
                'h-full transition-colors hover:border-primary/50 hover:bg-muted/30',
                isSelected && 'border-primary ring-2 ring-primary/20',
              )}
            >
              <CardHeader className="space-y-3">
                <div
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-full',
                    bgColor,
                  )}
                >
                  {icon}
                </div>
                <div>
                  <CardTitle className="text-base">{copy.title}</CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed">
                    {copy.description}
                  </CardDescription>
                </div>
              </CardHeader>
            </Card>
          </button>
        )
      })}
    </div>
  )
}
