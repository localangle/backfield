import { useCallback, useEffect, useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import {
  deleteOrganizationIntegrationSecret,
  listOrganizationIntegrationSecretMetadata,
  putOrganizationIntegrationSecret,
} from '@/lib/core-api'
import { PLATFORM_INTEGRATION_KEYS } from '@/lib/platform-integration-keys'

/** Shown when a secret exists server-side and the field is empty (write-only UI). */
const STORED_SECRET_PLACEHOLDER = 'Secret on file — paste to replace'

function StatusBadge({ configured }: { configured: boolean }) {
  return (
    <Badge variant={configured ? 'success' : 'secondary'}>
      {configured ? 'Configured' : 'Not set'}
    </Badge>
  )
}

export default function OrgIntegrationsSettings() {
  const { organizationId } = useAuth()
  const [configuredKeys, setConfiguredKeys] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [pelias, setPelias] = useState('')
  const [geocodio, setGeocodio] = useState('')
  const [brave, setBrave] = useState('')
  const [awsId, setAwsId] = useState('')
  const [awsSecret, setAwsSecret] = useState('')
  const [awsSession, setAwsSession] = useState('')

  const reload = useCallback(async () => {
    if (organizationId == null) return
    const rows = await listOrganizationIntegrationSecretMetadata(organizationId)
    const allowed = new Set<string>(Object.values(PLATFORM_INTEGRATION_KEYS))
    const next = new Set(rows.map((r) => r.integration_key).filter((k) => allowed.has(k)))
    setConfiguredKeys(next)
  }, [organizationId])

  useEffect(() => {
    if (organizationId == null) {
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        await reload()
      } catch (e) {
        if (!cancelled) setError('Could not load integration settings')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [organizationId, reload])

  const s3Complete = useMemo(
    () =>
      configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3AccessKeyId) &&
      configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3SecretAccessKey),
    [configuredKeys],
  )

  const savePlatform = async (integrationKey: string, value: string) => {
    if (organizationId == null) return
    try {
      setSaving(true)
      setError(null)
      await putOrganizationIntegrationSecret(organizationId, integrationKey, { value })
      await reload()
      return true
    } catch (e) {
      setError('Could not save')
      console.error(e)
      return false
    } finally {
      setSaving(false)
    }
  }

  const removePlatform = async (integrationKey: string) => {
    if (organizationId == null) return
    try {
      setSaving(true)
      setError(null)
      await deleteOrganizationIntegrationSecret(organizationId, integrationKey)
      await reload()
    } catch (e) {
      setError('Could not remove')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (organizationId == null) {
    return <p className="text-sm text-muted-foreground">Sign in to manage integrations.</p>
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <div className="w-full max-w-none min-w-0 space-y-10">
      <p className="text-sm text-muted-foreground">
        Organization defaults for geocoding, web search, and cloud storage. Projects can override
        these on each project’s Integrations tab.
      </p>

      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="divide-y divide-border">
      {/* Geocoding */}
      <section className="space-y-4 pb-10" aria-labelledby="integrations-geocoding-heading">
        <h2 id="integrations-geocoding-heading" className="text-lg font-semibold tracking-tight">
          Geocoding
        </h2>
        <p className="text-sm text-muted-foreground max-w-prose">
          Backfield supports the use of{' '}
          <a
            href="https://geocode.earth/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            Geocode Earth
          </a>{' '}
          and{' '}
          <a
            href="https://www.geocod.io/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            Geocodio
          </a>{' '}
          to enrich extracted place data. Both are based on open data and allow results to be stored.{' '}
          <a
            href="https://nominatim.org/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            Nominatim
          </a>{' '}
          is used as a fallback.
        </p>
        <div className="flex flex-col gap-4 w-full">
          <Card className="w-full">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Geocode Earth</CardTitle>
                <StatusBadge configured={configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodeEarth)} />
              </div>
              <CardDescription>Primary geocoding service. Free trial available.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="org-pelias">API key</Label>
                <Input
                  id="org-pelias"
                  type="password"
                  autoComplete="off"
                  value={pelias}
                  onChange={(e) => setPelias(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodeEarth) && !pelias.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={saving || !pelias.trim()}
                  onClick={async () => {
                    const ok = await savePlatform(PLATFORM_INTEGRATION_KEYS.geocodeEarth, pelias.trim())
                    if (ok) setPelias('')
                  }}
                >
                  Save
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving || !configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodeEarth)}
                  onClick={() => void removePlatform(PLATFORM_INTEGRATION_KEYS.geocodeEarth)}
                >
                  Remove
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="w-full">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Geocodio</CardTitle>
                <StatusBadge configured={configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodio)} />
              </div>
              <CardDescription>
                Secondary geocoding service. Useful for intersections and other special cases. Free trial
                available.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="org-gc">API key</Label>
                <Input
                  id="org-gc"
                  type="password"
                  autoComplete="off"
                  value={geocodio}
                  onChange={(e) => setGeocodio(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodio) && !geocodio.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={saving || !geocodio.trim()}
                  onClick={async () => {
                    const ok = await savePlatform(PLATFORM_INTEGRATION_KEYS.geocodio, geocodio.trim())
                    if (ok) setGeocodio('')
                  }}
                >
                  Save
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving || !configuredKeys.has(PLATFORM_INTEGRATION_KEYS.geocodio)}
                  onClick={() => void removePlatform(PLATFORM_INTEGRATION_KEYS.geocodio)}
                >
                  Remove
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="w-full">
            <CardHeader>
              <CardTitle className="text-base">Built-in geocoding helpers</CardTitle>
              <CardDescription>
                These services are always available for flows that use them. No API key is required.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Badge variant="outline">Nominatim</Badge>
              <Badge variant="outline">Overpass</Badge>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Search */}
      <section className="space-y-4 py-10" aria-labelledby="integrations-search-heading">
        <h2 id="integrations-search-heading" className="text-lg font-semibold tracking-tight">
          Search
        </h2>
        <p className="text-sm text-muted-foreground max-w-prose">
          Backfield supports the use of{' '}
          <a
            href="https://brave.com/search/api/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            Brave Search
          </a>{' '}
          to gather metadata that improves the accuracy of geocoding and gathers other metadata.{' '}
          <a
            href="https://duckduckgo.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline-offset-4 hover:underline"
          >
            DuckDuckGo
          </a>{' '}
          is used as a fallback.
        </p>
        <div className="flex flex-col gap-4 w-full">
          <Card className="w-full">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Brave Search</CardTitle>
                <StatusBadge configured={configuredKeys.has(PLATFORM_INTEGRATION_KEYS.braveSearch)} />
              </div>
              <CardDescription>Optional richer web results where the flow uses Brave.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="org-brave">API key</Label>
                <Input
                  id="org-brave"
                  type="password"
                  autoComplete="off"
                  value={brave}
                  onChange={(e) => setBrave(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.braveSearch) && !brave.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={saving || !brave.trim()}
                  onClick={async () => {
                    const ok = await savePlatform(PLATFORM_INTEGRATION_KEYS.braveSearch, brave.trim())
                    if (ok) setBrave('')
                  }}
                >
                  Save
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving || !configuredKeys.has(PLATFORM_INTEGRATION_KEYS.braveSearch)}
                  onClick={() => void removePlatform(PLATFORM_INTEGRATION_KEYS.braveSearch)}
                >
                  Remove
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="w-full">
            <CardHeader>
              <CardTitle className="text-base">Web search fallback</CardTitle>
              <CardDescription>
                When Brave Search is not configured, flows that need search fall back automatically.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Badge variant="outline">DuckDuckGo (no API key)</Badge>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Storage */}
      <section className="space-y-4 pt-10 pb-0" aria-labelledby="integrations-storage-heading">
        <h2 id="integrations-storage-heading" className="text-lg font-semibold tracking-tight">
          Storage
        </h2>
        <div className="flex flex-col gap-4 w-full">
          <Card className="w-full">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Amazon S3</CardTitle>
                <StatusBadge configured={s3Complete} />
              </div>
              <CardDescription>
                Access keys for flows that read from S3. Bucket and prefix stay on each flow node.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="org-aws-id">Access key ID</Label>
                <Input
                  id="org-aws-id"
                  type="password"
                  autoComplete="off"
                  value={awsId}
                  onChange={(e) => setAwsId(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3AccessKeyId) && !awsId.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div>
                <Label htmlFor="org-aws-sec">Secret access key</Label>
                <Input
                  id="org-aws-sec"
                  type="password"
                  autoComplete="off"
                  value={awsSecret}
                  onChange={(e) => setAwsSecret(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3SecretAccessKey) &&
                    !awsSecret.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div>
                <Label htmlFor="org-aws-st">Session token (optional)</Label>
                <Input
                  id="org-aws-st"
                  type="password"
                  autoComplete="off"
                  value={awsSession}
                  onChange={(e) => setAwsSession(e.target.value)}
                  disabled={saving}
                  placeholder={
                    configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3SessionToken) &&
                    !awsSession.trim()
                      ? STORED_SECRET_PLACEHOLDER
                      : undefined
                  }
                  className="font-mono text-sm mt-1 w-full"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={saving || !awsId.trim() || !awsSecret.trim()}
                  onClick={async () => {
                    if (organizationId == null) return
                    setSaving(true)
                    setError(null)
                    try {
                      await putOrganizationIntegrationSecret(organizationId, PLATFORM_INTEGRATION_KEYS.s3AccessKeyId, {
                        value: awsId.trim(),
                      })
                      await putOrganizationIntegrationSecret(
                        organizationId,
                        PLATFORM_INTEGRATION_KEYS.s3SecretAccessKey,
                        { value: awsSecret.trim() },
                      )
                      if (awsSession.trim()) {
                        await putOrganizationIntegrationSecret(
                          organizationId,
                          PLATFORM_INTEGRATION_KEYS.s3SessionToken,
                          { value: awsSession.trim() },
                        )
                      } else if (configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3SessionToken)) {
                        await deleteOrganizationIntegrationSecret(
                          organizationId,
                          PLATFORM_INTEGRATION_KEYS.s3SessionToken,
                        )
                      }
                      setAwsId('')
                      setAwsSecret('')
                      setAwsSession('')
                      await reload()
                    } catch (e) {
                      setError('Could not save S3 keys')
                      console.error(e)
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  Save S3 keys
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving || !s3Complete}
                  onClick={async () => {
                    if (organizationId == null) return
                    setSaving(true)
                    setError(null)
                    try {
                      await deleteOrganizationIntegrationSecret(
                        organizationId,
                        PLATFORM_INTEGRATION_KEYS.s3AccessKeyId,
                      )
                      await deleteOrganizationIntegrationSecret(
                        organizationId,
                        PLATFORM_INTEGRATION_KEYS.s3SecretAccessKey,
                      )
                      if (configuredKeys.has(PLATFORM_INTEGRATION_KEYS.s3SessionToken)) {
                        await deleteOrganizationIntegrationSecret(
                          organizationId,
                          PLATFORM_INTEGRATION_KEYS.s3SessionToken,
                        )
                      }
                      await reload()
                    } catch (e) {
                      setError('Could not remove S3 keys')
                      console.error(e)
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  Remove S3 keys
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
      </div>
    </div>
  )
}
