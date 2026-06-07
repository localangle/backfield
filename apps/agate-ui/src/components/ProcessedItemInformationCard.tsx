import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { patchProcessedItemOverlay, type ProcessedItem } from '@/lib/api'
import {
  applyArticleFieldsToOverlay,
  ARTICLE_FIELD_KEYS,
  ARTICLE_FIELD_LABELS,
  articleFieldsEqual,
  readArticleFieldsFromProcessedItem,
  type ArticleFieldKey,
  type ArticleFields,
} from '@/lib/review/content/articleFields'
import { isBatchFileSource, processedItemSourceLabel } from '@/lib/review/content/sourceDisplay'
import { formatDate } from '@/lib/utils'
import {
  connectionsStatusLabel,
  formatConnectionsDetail,
  getConnectionsStatusColor,
  shouldShowConnectionsSummary,
} from '@/lib/review/content/connectionsDisplay'
import {
  formatSemanticIndexingDetail,
  semanticIndexingStatusLabel,
  shouldShowSemanticIndexingSummary,
} from '@/lib/review/content/semanticIndexingDisplay'
import { CheckCircle, Clock, ExternalLink, FileText, Loader2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

function getSemanticIndexingStatusColor(status: string) {
  switch (status) {
    case 'succeeded':
      return 'text-green-700 dark:text-green-400'
    case 'partial':
      return 'text-amber-700 dark:text-amber-400'
    case 'failed':
      return 'text-red-700 dark:text-red-400'
    case 'running':
    case 'pending':
      return 'text-blue-700 dark:text-blue-400'
    default:
      return 'text-muted-foreground'
  }
}

function getStatusColor(status: string) {
  switch (status) {
    case 'succeeded':
      return 'bg-green-100 text-green-800 border-green-200'
    case 'failed':
    case 'timed_out':
      return 'bg-red-100 text-red-800 border-red-200'
    case 'running':
      return 'bg-blue-100 text-blue-800 border-blue-200'
    case 'pending':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200'
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'succeeded':
      return <CheckCircle className="h-4 w-4" />
    case 'failed':
    case 'timed_out':
      return <XCircle className="h-4 w-4" />
    case 'running':
    case 'pending':
      return <Clock className="h-4 w-4" />
    default:
      return null
  }
}

function formatEstimatedAiCost(item: ProcessedItem): ReactNode {
  if (item.estimated_ai_cost === undefined || item.estimated_ai_cost === null) {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <>
      {Number(item.estimated_ai_cost).toLocaleString(undefined, {
        style: 'currency',
        currency: item.estimated_ai_cost_currency || 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}
      {item.estimated_ai_cost_incomplete ? (
        <span
          className="text-amber-700 dark:text-amber-400 ml-1"
          title="Estimate may be incomplete"
        >
          *
        </span>
      ) : null}
    </>
  )
}

function ArticleFieldReadValue({
  fieldKey,
  value,
  interactive,
  onActivateEdit,
}: {
  fieldKey: ArticleFieldKey
  value: string
  interactive: boolean
  onActivateEdit: () => void
}) {
  const shellClass = cn(
    'rounded-md px-2 py-1.5 -mx-2 min-h-[2rem] flex items-center',
    interactive &&
      'cursor-pointer transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  )

  const content = (() => {
    if (!value.trim()) {
      return (
        <p className="text-sm text-muted-foreground">{interactive ? 'Click to add' : '—'}</p>
      )
    }
    if (fieldKey === 'url' && !interactive) {
      return (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary hover:underline break-all inline-flex items-start gap-1"
        >
          {value}
          <ExternalLink className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
        </a>
      )
    }
    if (fieldKey === 'url') {
      return <p className="text-sm break-all font-mono">{value}</p>
    }
    return <p className="text-sm break-words">{value}</p>
  })()

  if (!interactive) {
    return <div className={shellClass}>{content}</div>
  }

  return (
    <div
      role="button"
      tabIndex={0}
      className={shellClass}
      onClick={onActivateEdit}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onActivateEdit()
        }
      }}
      aria-label={`Edit ${ARTICLE_FIELD_LABELS[fieldKey]}`}
    >
      {content}
    </div>
  )
}

export interface ProcessedItemInformationCardProps {
  runId: string
  item: ProcessedItem
  onItemUpdated: (item: ProcessedItem) => void
  /** When the Places tab has unsaved map/overlay edits. */
  reviewDirty?: boolean
  /** When a rerun is in flight; story detail fields cannot be edited. */
  reviewLocked?: boolean
}

export function ProcessedItemInformationCard({
  runId,
  item,
  onItemUpdated,
  reviewDirty = false,
  reviewLocked = false,
}: ProcessedItemInformationCardProps) {
  const { showError, showConfirm } = useAppMessage()
  const [fields, setFields] = useState<ArticleFields>(() => readArticleFieldsFromProcessedItem(item))
  const [baseline, setBaseline] = useState<ArticleFields>(() => readArticleFieldsFromProcessedItem(item))
  const [editingKey, setEditingKey] = useState<ArticleFieldKey | null>(null)
  const [saving, setSaving] = useState(false)

  const syncKey = `${runId}:${item.id}:${item.overlay_version}`

  useEffect(() => {
    const next = readArticleFieldsFromProcessedItem(item)
    setFields(next)
    setBaseline(next)
    setEditingKey(null)
  }, [syncKey, item])

  useEffect(() => {
    if (reviewLocked) {
      setEditingKey(null)
    }
  }, [reviewLocked])

  const persistFields = useCallback(
    async (nextFields: ArticleFields): Promise<boolean> => {
      if (articleFieldsEqual(nextFields, baseline)) return true
      if (reviewDirty) {
        const ok = await showConfirm(
          'Save your place review changes before updating story details, or continue and keep those edits only on this page until you save them.',
          {
            title: 'Unsaved place review',
            confirmLabel: 'Save story details anyway',
            cancelLabel: 'Stay',
            destructive: false,
          },
        )
        if (!ok) {
          setFields(baseline)
          return false
        }
      }
      setSaving(true)
      try {
        const overlay = applyArticleFieldsToOverlay(item.overlay, nextFields)
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          overlay,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        const saved = readArticleFieldsFromProcessedItem(updated)
        setFields(saved)
        setBaseline(saved)
        return true
      } catch (e) {
        console.error('Failed to save story details:', e)
        showError('We could not save your changes. Check your connection and try again.', {
          title: 'Could not save',
        })
        setFields(baseline)
        return false
      } finally {
        setSaving(false)
      }
    },
    [
      baseline,
      item.id,
      item.overlay,
      item.overlay_version,
      onItemUpdated,
      reviewDirty,
      runId,
      showConfirm,
      showError,
    ],
  )

  const commitFieldEdit = useCallback(
    async (key: ArticleFieldKey) => {
      const saved = await persistFields(fields)
      if (saved) {
        setEditingKey(null)
      }
    },
    [fields, persistFields],
  )

  const cancelFieldEdit = useCallback(
    (key: ArticleFieldKey) => {
      setFields((prev) => ({ ...prev, [key]: baseline[key] }))
      setEditingKey(null)
    },
    [baseline],
  )

  const editable = !item.synthetic && !reviewLocked
  const semanticIndexing = item.semantic_indexing
  const showSemanticIndexing = shouldShowSemanticIndexingSummary(semanticIndexing)
  const connections = item.connections
  const showConnections = shouldShowConnectionsSummary(connections)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Item Information
          <Badge variant="outline" className={getStatusColor(item.status)}>
            {getStatusIcon(item.status)}
            <span className="ml-1 capitalize">{item.status}</span>
          </Badge>
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Saving" />
          ) : null}
        </CardTitle>
        {(isBatchFileSource(item.source_file) || processedItemSourceLabel(item)) && (
          <CardDescription
            className={`text-xs ${isBatchFileSource(item.source_file) ? 'font-mono' : ''}`}
          >
            <FileText className="inline h-3 w-3 mr-1" />
            {processedItemSourceLabel(item) ?? item.source_file}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {ARTICLE_FIELD_KEYS.map((key) => {
            const isEditing = editingKey === key
            const inputId = `article-${key}`
            return (
              <div key={key} className="space-y-1">
                <label htmlFor={isEditing ? inputId : undefined} className="text-sm font-medium text-muted-foreground">
                  {ARTICLE_FIELD_LABELS[key]}
                </label>
                {isEditing ? (
                  <Input
                    id={inputId}
                    autoFocus
                    value={fields[key]}
                    disabled={saving}
                    onChange={(e) => setFields((prev) => ({ ...prev, [key]: e.target.value }))}
                    onBlur={() => void commitFieldEdit(key)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void commitFieldEdit(key)
                      }
                      if (e.key === 'Escape') {
                        e.preventDefault()
                        cancelFieldEdit(key)
                      }
                    }}
                    className={key === 'url' ? 'font-mono text-sm' : undefined}
                  />
                ) : (
                  <ArticleFieldReadValue
                    fieldKey={key}
                    value={fields[key]}
                    interactive={editable && !saving}
                    onActivateEdit={() => setEditingKey(key)}
                  />
                )}
              </div>
            )
          })}
        </div>

        <div className="border-t border-border pt-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Created</label>
              <p className="text-sm mt-0.5">{formatDate(item.created_at)}</p>
            </div>
            {item.status !== 'pending' ? (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Completed</label>
                <p className="text-sm mt-0.5">{formatDate(item.updated_at)}</p>
              </div>
            ) : null}
            <div>
              <label className="text-sm font-medium text-muted-foreground">Estimated AI cost</label>
              <p className="text-sm tabular-nums mt-0.5">{formatEstimatedAiCost(item)}</p>
              {item.estimated_ai_cost_incomplete ? (
                <p className="text-xs text-muted-foreground mt-1">
                  The asterisk means part of this estimate may be missing.
                </p>
              ) : null}
            </div>
            {showSemanticIndexing && semanticIndexing ? (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Semantic search</label>
                <p
                  className={cn(
                    'text-sm mt-0.5',
                    getSemanticIndexingStatusColor(semanticIndexing.status),
                  )}
                >
                  {semanticIndexingStatusLabel(semanticIndexing.status)}
                </p>
                {formatSemanticIndexingDetail(semanticIndexing) ? (
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatSemanticIndexingDetail(semanticIndexing)}
                  </p>
                ) : null}
                {semanticIndexing.indexed_at ? (
                  <p className="text-xs text-muted-foreground mt-1">
                    Last indexed {formatDate(semanticIndexing.indexed_at)}
                  </p>
                ) : null}
              </div>
            ) : null}
            {showConnections && connections ? (
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Automatic connections
                </label>
                <p
                  className={cn(
                    'text-sm mt-0.5',
                    getConnectionsStatusColor(connections.status),
                  )}
                >
                  {connectionsStatusLabel(connections.status)}
                </p>
                {formatConnectionsDetail(connections) ? (
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatConnectionsDetail(connections)}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
