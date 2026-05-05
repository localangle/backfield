import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Loader2 } from 'lucide-react'
import { fetchMe, listOrganizationAiModels, type AiModelConfigSummary } from '@/lib/core-api'

export default function AiModelsSettingsPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<AiModelConfigSummary[]>([])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const me = await fetchMe()
        const oid = me.organization_id
        if (oid == null) {
          throw new Error('No organization on your session.')
        }
        const rows = await listOrganizationAiModels(oid)
        if (!cancelled) setModels(rows)
      } catch (e: unknown) {
        if (!cancelled) {
          setModels([])
          setError(e instanceof Error ? e.message : 'Could not load catalog.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">AI models</h1>
        <p className="text-muted-foreground mt-2">
          Approved models for your organization appear below. Project-level availability and keys
          can be adjusted from each project&apos;s settings when that project is selected.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Organization catalog</CardTitle>
          <CardDescription>
            Changes to pricing, credentials, and tests use the Core API settings flows (this page
            lists what is active today).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading models…
            </div>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : models.length === 0 ? (
            <p className="text-sm text-muted-foreground">No models configured yet.</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {models.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div>
                    <div className="font-medium">{m.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {m.provider} · {m.provider_model_id}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="secondary">{m.status}</Badge>
                    {m.latest_test_status ? (
                      <Badge variant="outline">Last test: {m.latest_test_status}</Badge>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
