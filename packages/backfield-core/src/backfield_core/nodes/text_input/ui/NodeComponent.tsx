import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface TextInputData {
  text: string
}

function TextInputNode({ data, selected }: NodeProps<TextInputData>) {
  // Truncate text for display in the node
  const displayText = data.text.length > 100 
    ? `${data.text.substring(0, 100)}...` 
    : data.text
  const icon = getNodeIcon('TextInput', 'h-4 w-4')
  const bgColor = getNodeBgColor('TextInput')

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Text Input
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="min-h-[100px] p-3 bg-muted rounded-md text-sm text-muted-foreground">
          {data.text ? (
            <div className="whitespace-pre-wrap break-words">
              {displayText}
            </div>
          ) : (
            <div className="text-center text-muted-foreground/60">
              Click to edit text in panel
            </div>
          )}
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(TextInputNode)
