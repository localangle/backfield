import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import {
  listAiCredentialsCatalog,
  listOrganizationIntegrationSecretMetadata,
} from '@/lib/core-api'
import { isOrganizationSetupIncomplete } from '@/lib/orgSetupStatus'

export default function OrganizationSetupBanner() {
  const location = useLocation()
  const { organizationId, isOrgAdmin } = useAuth()
  const [showBanner, setShowBanner] = useState(false)

  const onSettingsRoute = location.pathname.startsWith('/settings')

  const load = useCallback(async () => {
    if (organizationId == null || !isOrgAdmin) {
      setShowBanner(false)
      return
    }
    try {
      const [aiCredentials, integrationMetadata] = await Promise.all([
        listAiCredentialsCatalog(organizationId),
        listOrganizationIntegrationSecretMetadata(organizationId),
      ])
      setShowBanner(
        isOrganizationSetupIncomplete({ aiCredentials, integrationMetadata }),
      )
    } catch {
      setShowBanner(false)
    }
  }, [organizationId, isOrgAdmin])

  useEffect(() => {
    void load()
  }, [load, location.pathname])

  if (!showBanner || onSettingsRoute) {
    return null
  }

  return (
    <Alert
      variant="default"
      className="mb-6 border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-50"
    >
      <AlertTriangle className="h-4 w-4 text-amber-700 dark:text-amber-200" aria-hidden />
      <AlertTitle>Finish setup in Settings</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p>
          Add model credentials and any integrations your workflows need before running flows.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0 border-amber-300 bg-background/80 hover:bg-background dark:border-amber-800"
          asChild
        >
          <Link to="/settings">Open Settings</Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}
