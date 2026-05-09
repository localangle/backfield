import { useCallback, useEffect, useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle } from 'lucide-react'
import {
  deleteProjectApiKey,
  listProjectApiKeys,
  setProjectApiKey,
  type ApiKey,
} from '@/lib/api'
import { listOrganizationIntegrationSecretMetadata } from '@/lib/core-api'
import { PLATFORM_INTEGRATION_KEYS, PROJECT_OVERRIDE_ENV_KEYS } from '@/lib/platform-integration-keys'

const STORED_SECRET_PLACEHOLDER = 'Secret on file — paste to replace'

/** Maps project env override keys to organization integration_secret keys (metadata only). */
const OVERRIDE_TO_ORG_PLATFORM_KEY: Record<(typeof PROJECT_OVERRIDE_ENV_KEYS)[number], string> = {
  PELIAS_API_KEY: PLATFORM_INTEGRATION_KEYS.geocodeEarth,
  GEOCODIO_API_KEY: PLATFORM_INTEGRATION_KEYS.geocodio,
  BRAVE_SEARCH_API_KEY: PLATFORM_INTEGRATION_KEYS.braveSearch,
  AWS_ACCESS_KEY_ID: PLATFORM_INTEGRATION_KEYS.s3AccessKeyId,
  AWS_SECRET_ACCESS_KEY: PLATFORM_INTEGRATION_KEYS.s3SecretAccessKey,
  AWS_SESSION_TOKEN: PLATFORM_INTEGRATION_KEYS.s3SessionToken,
}

const OVERRIDE_LABELS: Record<string, { title: string; hint: string }> = {
  PELIAS_API_KEY: {
    title: 'Geocode Earth',
    hint: 'Overrides the organization default for this project only.',
  },
  GEOCODIO_API_KEY: {
    title: 'Geocodio',
    hint: 'Overrides the organization default for this project only.',
  },
  BRAVE_SEARCH_API_KEY: {
    title: 'Brave Search',
    hint: 'Overrides the organization default for this project only.',
  },
  AWS_ACCESS_KEY_ID: {
    title: 'S3 access key ID',
    hint: 'Use together with the secret key. Bucket and path stay on the flow node.',
  },
  AWS_SECRET_ACCESS_KEY: {
    title: 'S3 secret access key',
    hint: 'Use together with the access key ID.',
  },
  AWS_SESSION_TOKEN: {
    title: 'S3 session token',
    hint: 'Optional; for temporary credentials.',
  },
}

/** Project-specific key saved for this row (replaces organization default for this project). */
function OverriddenBadge() {
  return (
    <Badge
      variant="outline"
      className="border-amber-300 bg-amber-50 text-amber-950 shadow-none dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100"
    >
      Overridden
    </Badge>
  )
}

/** Organization Settings → Integrations has a saved key for this slot (no project override). */
function OrgDefaultStatusBadge({ orgHasKey }: { orgHasKey: boolean }) {
  return (
    <Badge variant={orgHasKey ? 'success' : 'secondary'}>
      {orgHasKey ? 'Configured' : 'Not set'}
    </Badge>
  )
}

export default function ProjectDetailIntegrationsTab({
  projectId,
  organizationId,
  isOrgAdmin,
}: {
  projectId: number
  organizationId: number | null
  isOrgAdmin: boolean
}) {
  const [orgConfigured, setOrgConfigured] = useState<Set<string>>(new Set())
  const [projectKeys, setProjectKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const reload = useCallback(async () => {
    const keys = await listProjectApiKeys(projectId)
    setProjectKeys(keys)
    if (isOrgAdmin && organizationId != null) {
      try {
        const meta = await listOrganizationIntegrationSecretMetadata(organizationId)
        const allowed = new Set<string>(Object.values(PLATFORM_INTEGRATION_KEYS))
        const platform = new Set(meta.map((m) => m.integration_key).filter((k) => allowed.has(k)))
        setOrgConfigured(platform)
      } catch {
        setOrgConfigured(new Set())
      }
    } else {
      setOrgConfigured(new Set())
    }
  }, [projectId, organizationId, isOrgAdmin])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        await reload()
      } catch (e) {
        if (!cancelled) setError('Could not load integrations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [reload])

  const projectKeyNames = useMemo(
    () => new Set(projectKeys.map((k) => k.key_name)),
    [projectKeys],
  )

  /** Org integration metadata is only available to organization admins (Core API). */
  const showOrgDefaultPills = isOrgAdmin && organizationId != null

  const setDraft = (keyName: string, value: string) => {
    setDrafts((d) => ({ ...d, [keyName]: value }))
  }

  const saveOverride = async (keyName: string) => {
    const v = (drafts[keyName] ?? '').trim()
    if (!v) return
    try {
      setSaving(true)
      setError(null)
      await setProjectApiKey(projectId, { key_name: keyName, value: v })
      setDraft(keyName, '')
      await reload()
    } catch (e) {
      setError('Could not save')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const removeOverride = async (keyName: string) => {
    try {
      setSaving(true)
      setError(null)
      await deleteProjectApiKey(projectId, keyName)
      await reload()
    } catch (e) {
      setError('Could not remove')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <div className="w-full min-w-0 space-y-6">
      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <p className="text-sm text-muted-foreground">
        Configure geocoding, search, and S3 credentials for this project. Values here replace
        organization defaults for runs in this project only. API access keys stay on the Keys tab.
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Project overrides</CardTitle>
          <CardDescription>
            Leave blank and remove overrides to rely on organization defaults.{' '}
            <span className="font-medium text-foreground">Configured</span> means this project uses the
            key from Settings → Integrations;{' '}
            <span className="font-medium text-foreground">Overridden</span> means this project has its own
            key saved here.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          {PROJECT_OVERRIDE_ENV_KEYS.map((keyName) => {
            const meta = OVERRIDE_LABELS[keyName]
            const has = projectKeyNames.has(keyName)
            const draft = drafts[keyName] ?? ''
            const draftEmpty = !draft.trim()
            const orgHasKeyForSlot = orgConfigured.has(OVERRIDE_TO_ORG_PLATFORM_KEY[keyName])
            return (
              <div key={keyName} className="space-y-2 border-b border-border pb-6 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-medium">{meta.title}</h4>
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {has ? (
                      <OverriddenBadge />
                    ) : showOrgDefaultPills ? (
                      <OrgDefaultStatusBadge orgHasKey={orgHasKeyForSlot} />
                    ) : null}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">{meta.hint}</p>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <div className="flex-1 min-w-0">
                    <Label htmlFor={`ov-${keyName}`} className="sr-only">
                      {meta.title}
                    </Label>
                    <Input
                      id={`ov-${keyName}`}
                      type="password"
                      autoComplete="off"
                      value={draft}
                      onChange={(e) => setDraft(keyName, e.target.value)}
                      placeholder={
                        has && draftEmpty
                          ? STORED_SECRET_PLACEHOLDER
                          : !has
                            ? 'Paste key'
                            : undefined
                      }
                      disabled={saving}
                      className="font-mono text-sm"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <Button
                      type="button"
                      size="sm"
                      disabled={saving || !(drafts[keyName] ?? '').trim()}
                      onClick={() => void saveOverride(keyName)}
                    >
                      Save
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={saving || !has}
                      onClick={() => void removeOverride(keyName)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              </div>
            )
          })}
        </CardContent>
      </Card>
    </div>
  )
}
