import { X, CheckCircle, Clock, Loader2, ExternalLink, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Link } from 'react-router-dom'
import type { Run } from '@/lib/api'

interface RunPanelProps {
  onClose: () => void
  running?: boolean
  currentRun?: Run | null
}

export default function RunPanel({
  onClose,
  running,
  currentRun,
}: RunPanelProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'completed':
        return 'bg-green-100 text-green-800 border-green-200'
      case 'completed_with_errors':
        return 'bg-orange-100 text-orange-800 border-orange-200'
      case 'pending':
        return 'bg-gray-100 text-gray-800 border-gray-200'
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'completed':
        return <CheckCircle className="h-4 w-4" />
      case 'completed_with_errors':
        return <AlertTriangle className="h-4 w-4" />
      case 'pending':
        return <Clock className="h-4 w-4" />
      default:
        return <Clock className="h-4 w-4" />
    }
  }

  const formatStatusLabel = (status: string) =>
    status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="absolute top-0 right-0 h-full w-96 bg-background/95 backdrop-blur-sm border-l shadow-lg flex flex-col z-10 slide-in-from-right">
      <div className="flex items-center justify-between p-4 border-b">
        <div>
          <h3 className="font-semibold text-lg">Flow Execution</h3>
          <p className="text-sm text-muted-foreground">Run logs and outputs</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {running && !currentRun && (
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Starting flow execution...</span>
              </div>
            </CardContent>
          </Card>
        )}

        {currentRun && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Run #{currentRun.id}</CardTitle>
                <div className="flex items-center gap-2">
                  <Link to={`/runs/${currentRun.id}`}>
                    <Button variant="ghost" size="sm" className="h-6 px-2">
                      <ExternalLink className="h-3 w-3 mr-1" />
                      View Details
                    </Button>
                  </Link>
                  <Badge className={getStatusColor(currentRun.status)}>
                    <div className="flex items-center gap-1">
                      {getStatusIcon(currentRun.status)}
                      {formatStatusLabel(currentRun.status)}
                    </div>
                  </Badge>
                </div>
              </div>
              <CardDescription>
                Started: {new Date(currentRun.created_at).toLocaleString()}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {currentRun.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <h4 className="text-sm font-medium text-red-800 mb-2">Error</h4>
                  <p className="text-sm text-red-700 font-mono">{currentRun.error}</p>
                </div>
              )}

              {currentRun.output && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Output</h4>
                  <div className="p-3 bg-muted rounded-md">
                    <pre className="text-xs overflow-auto max-h-64">
                      {JSON.stringify(currentRun.output, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {currentRun.input && Object.keys(currentRun.input).length > 0 && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Input</h4>
                  <div className="p-3 bg-muted rounded-md">
                    <pre className="text-xs overflow-auto max-h-32">
                      {JSON.stringify(currentRun.input, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {!running && !currentRun && (
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground text-center">
                Click "Run Flow" to execute this flow and see results here.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
