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
  flowName?: string
}

function runCardTitle(status: string, flowName: string): string {
  const name = flowName.trim() || 'Untitled flow'
  switch (status) {
    case 'running':
    case 'pending':
      return `Running ${name}`
    case 'completed':
    case 'completed_with_errors':
      return `Completed ${name}`
    default:
      return name
  }
}

export default function RunPanel({
  onClose,
  running,
  currentRun,
  flowName = 'Untitled flow',
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
      <div className="flex items-center justify-end p-3 border-b">
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {running && !currentRun && (
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Starting {flowName.trim() || 'your flow'}…</span>
              </div>
            </CardContent>
          </Card>
        )}

        {currentRun && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-base">
                  {runCardTitle(currentRun.status, flowName)}
                </CardTitle>
                <Badge variant="outline" className={getStatusColor(currentRun.status)}>
                  <div className="flex items-center gap-1">
                    {getStatusIcon(currentRun.status)}
                    {formatStatusLabel(currentRun.status)}
                  </div>
                </Badge>
              </div>
              <CardDescription>
                Started {new Date(currentRun.created_at).toLocaleString()}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Visit the run page to track status and review outputs.
              </p>
              <Button asChild className="w-full">
                <Link to={`/runs/${currentRun.id}`}>
                  Open run page
                  <ExternalLink className="h-4 w-4 ml-2" />
                </Link>
              </Button>

              {currentRun.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <h4 className="text-sm font-medium text-red-800 mb-2">Something went wrong</h4>
                  <p className="text-sm text-red-700">{currentRun.error}</p>
                  <p className="text-xs text-red-600 mt-2">
                    Open the run page for the full error details.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {!running && !currentRun && (
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground text-center">
                Click Run Flow to start. You&apos;ll see status here, then open the run page for
                full logs and results.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
