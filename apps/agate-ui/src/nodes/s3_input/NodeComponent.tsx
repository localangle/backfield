// Auto-injected metadata for S3Input
const nodeMetadata = {
  "type": "S3Input",
  "label": "S3 Input",
  "icon": "Archive",
  "color": "bg-blue-500",
  "description": "Load article text from JSON files in S3.",
  "category": "input",
  "inputs": [],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "bucket": "",
    "folder_path": "",
    "max_files": 500
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface S3InputData {
  bucket?: string
  folder_path?: string
}

function S3InputNode({ data, selected }: NodeProps<S3InputData>) {
  const bucketDisplay = data.bucket || 'No bucket configured'
  const folderDisplay = data.folder_path ? `/${data.folder_path}` : ''
  const icon = getNodeIcon('S3Input', 'h-4 w-4')
  const bgColor = getNodeBgColor('S3Input')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          S3 Input
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-xs text-gray-600">
          <div className="font-mono truncate" title={`s3://${bucketDisplay}${folderDisplay}`}>
            s3://{bucketDisplay.substring(0, 20)}
            {bucketDisplay.length > 20 ? '...' : ''}
            {folderDisplay}
          </div>
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

export default memo(S3InputNode)
