// Auto-injected metadata for S3Output
const nodeMetadata = {
  "type": "S3Output",
  "label": "S3 Output",
  "icon": "Archive",
  "color": "bg-slate-500",
  "description": "Save the results as JSON files in an S3 bucket.",
  "category": "output",
  "requiredUpstreamNodes": [],
  "inputs": [
    {
      "id": "data",
      "label": "Any Data",
      "type": "any",
      "required": true
    }
  ],
  "outputs": [],
  "defaultParams": {
    "bucket": "",
    "output_path": "",
    "public_read": false,
    "exclude": null,
    "include": null
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface S3OutputData {
  bucket?: string
  output_path?: string
}

function S3OutputNode({ data, selected }: NodeProps<S3OutputData>) {
  const bucketDisplay = data.bucket || 'No bucket configured'
  const folderDisplay = data.output_path ? `/${data.output_path}` : ''
  const icon = getNodeIcon('S3Output', 'h-4 w-4')
  const bgColor = getNodeBgColor('S3Output')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          S3 Output
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="data"
          className="w-3 h-3 bg-gray-700"
        />
        <div className="text-xs text-gray-600">
          <div className="font-mono truncate" title={`s3://${bucketDisplay}${folderDisplay}`}>
            s3://{bucketDisplay.substring(0, 20)}
            {bucketDisplay.length > 20 ? '...' : ''}
            {folderDisplay}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default memo(S3OutputNode)
