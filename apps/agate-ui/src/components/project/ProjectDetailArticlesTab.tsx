import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  listProjectProcessedItems,
  type ProjectProcessedItem,
} from '@/lib/api'
import { formatDate } from '@/lib/utils'
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Loader2,
  Search,
  XCircle,
} from 'lucide-react'

const PAGE_SIZE = 50
const SEARCH_DEBOUNCE_MS = 300

interface ProjectDetailArticlesTabProps {
  projectId: number
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    case 'succeeded':
      return 'bg-green-100 text-green-800 border-green-200'
    case 'failed':
    case 'timed_out':
      return 'bg-red-100 text-red-800 border-red-200'
    case 'pending':
      return 'bg-gray-100 text-gray-800 border-gray-200'
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200'
  }
}

function statusIcon(status: string) {
  switch (status) {
    case 'running':
      return <Loader2 className="h-4 w-4 animate-spin" />
    case 'succeeded':
      return <CheckCircle className="h-4 w-4" />
    case 'failed':
    case 'timed_out':
      return <XCircle className="h-4 w-4" />
    case 'pending':
      return <Clock className="h-4 w-4" />
    default:
      return <AlertTriangle className="h-4 w-4" />
  }
}

function shortRunId(runId: string): string {
  return runId.length > 8 ? `${runId.slice(0, 8)}…` : runId
}

export default function ProjectDetailArticlesTab({
  projectId,
}: ProjectDetailArticlesTabProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [items, setItems] = useState<ProjectProcessedItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(query.trim())
      setOffset(0)
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
  }, [query])

  const loadPage = useCallback(
    async (pageOffset: number) => {
      setLoading(true)
      setError(null)
      try {
        const page = await listProjectProcessedItems(projectId, {
          q: debouncedQuery || null,
          limit: PAGE_SIZE,
          offset: pageOffset,
        })
        setItems(page.items)
        setTotal(page.total)
        setOffset(page.offset)
      } catch (err) {
        console.error(err)
        setError('Could not load articles for this project.')
        setItems([])
        setTotal(0)
      } finally {
        setLoading(false)
      }
    },
    [projectId, debouncedQuery],
  )

  useEffect(() => {
    void loadPage(0)
  }, [loadPage])

  const hasQuery = debouncedQuery.length > 0
  const canPrev = offset > 0
  const canNext = offset + items.length < total

  return (
    <div className="space-y-4 w-full min-w-0">
      <p className="text-sm text-muted-foreground mb-1">
        Find stories processed in this project and open them for review.
      </p>

      <div className="relative max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by headline or URL"
          className="pl-9"
          aria-label="Search articles"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">{error}</p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              {hasQuery
                ? 'No articles match that search.'
                : 'No articles yet for this project.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <div className="w-full overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="border-b bg-muted/50">
                    <tr>
                      <th className="text-left p-3 sm:p-4 font-medium">Article</th>
                      <th className="text-left p-3 sm:p-4 font-medium">Status</th>
                      <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">
                        Flow
                      </th>
                      <th className="text-left p-3 sm:p-4 font-medium hidden md:table-cell">
                        Run
                      </th>
                      <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">
                        Processed
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr
                        key={item.id}
                        className="border-b last:border-b-0 hover:bg-muted/[0.07] cursor-pointer transition-colors"
                        onClick={() =>
                          navigate(`/runs/${item.run_id}/items/${item.id}`)
                        }
                      >
                        <td className="p-3 sm:p-4 align-top min-w-0">
                          <div className="font-medium break-words">{item.title}</div>
                          {item.url ? (
                            <div className="text-xs text-muted-foreground mt-1 truncate max-w-[28rem]">
                              {item.url}
                            </div>
                          ) : null}
                        </td>
                        <td className="p-3 sm:p-4 align-top">
                          <Badge
                            variant="outline"
                            className={`${statusBadgeClass(item.status)} w-fit`}
                          >
                            {statusIcon(item.status)}
                            <span className="ml-1 capitalize">
                              {item.status.replace(/_/g, ' ')}
                            </span>
                          </Badge>
                        </td>
                        <td className="p-3 sm:p-4 text-muted-foreground align-top hidden sm:table-cell">
                          {item.flow_name || '—'}
                        </td>
                        <td
                          className="p-3 sm:p-4 text-muted-foreground align-top hidden md:table-cell font-mono text-xs"
                          title={item.run_id}
                        >
                          {shortRunId(item.run_id)}
                        </td>
                        <td className="p-3 sm:p-4 text-muted-foreground align-top hidden sm:table-cell whitespace-nowrap">
                          {formatDate(item.created_at, {
                            dateStyle: 'medium',
                            timeStyle: 'short',
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {total > PAGE_SIZE ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                Showing {offset + 1}–{offset + items.length} of {total}
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!canPrev}
                  onClick={() => void loadPage(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!canNext}
                  onClick={() => void loadPage(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
