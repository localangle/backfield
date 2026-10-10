import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface PersonEnrichData {
  model?: string
  sources?: string[]
}

const SOURCE_LABELS: Record<string, string> = {
  wikidata: 'Wikidata',
  wikipedia: 'Wikipedia',
}

function PersonEnrichNode({ data, selected }: NodeProps<PersonEnrichData>) {
  const icon = getNodeIcon('PersonEnrich', 'h-4 w-4')
  const bgColor = getNodeBgColor('PersonEnrich')
  const modelLabel = data.model?.trim() ? data.model.trim() : 'Decision model not set'
  const sources = Array.isArray(data.sources) ? data.sources : ['wikidata', 'wikipedia']
  const sourceLabel = sources
    .map((source) => SOURCE_LABELS[source])
    .filter((label): label is string => Boolean(label))
    .join(', ')

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Person Enrich
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle type="target" position={Position.Left} id="people" className="w-3 h-3 bg-gray-700" />
        <div className="text-xs space-y-1 text-muted-foreground">
          <p>{modelLabel}</p>
          <p>{sourceLabel || 'No reference links selected'}</p>
        </div>
        <Handle type="source" position={Position.Right} id="people" className="w-3 h-3 bg-gray-700" />
      </CardContent>
    </Card>
  )
}

export default memo(PersonEnrichNode)
