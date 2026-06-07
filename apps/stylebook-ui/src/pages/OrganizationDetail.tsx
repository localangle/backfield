import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalOrganization,
  getCanonicalOrganization,
  getCanonicalOrganizationMentions,
  listCanonicalLinkedOrganizationSubstrates,
  patchCanonicalOrganization,
  unlinkOrganizationSubstrateFromCanonical,
  type CanonicalOrganization,
  type LinkedOrganizationMention,
  type LinkedOrganizationSubstrateItem,
} from "@/lib/api"
import {
  organizationTypeManualSelectOptions,
  placeExtractTypeLabel,
} from "@/lib/place-extract-type-label"
import { isStylebookApiNotFoundError } from "@/lib/stylebook-api/client"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { usePromptDeleteEmptyCanonical } from "@/lib/usePromptDeleteEmptyCanonical"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { useAppMessage } from "@/components/AppMessageProvider"
import { OrganizationCanonicalLinkModal } from "@/components/OrganizationCanonicalLinkModal"
import CanonicalDetailLayout from "@/components/CanonicalDetailLayout"
import OrganizationMetaTab from "@/components/OrganizationMetaTab"
import { organizationCanonicalDetailConfig } from "@/lib/entityConfigs/organization/canonicalDetail"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export default function OrganizationDetail() {
  const { showError, showConfirm } = useAppMessage()
  const {
    projectFilterSlug,
    filterScopeSuffix,
    stylebookSlug,
    catalogBasePath,
  } = useProjectCatalogScope()
  const [searchParams] = useSearchParams()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const evidenceProjectSlug = projectFilterSlug || ""

  const [organization, setOrganization] = useState<CanonicalOrganization | null>(null)
  const [substrates, setSubstrates] = useState<LinkedOrganizationSubstrateItem[]>([])
  const [mentions, setMentions] = useState<LinkedOrganizationMention[]>([])
  const [loading, setLoading] = useState(true)
  const [substratesLoading, setSubstratesLoading] = useState(false)
  const [mentionsLoading, setMentionsLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState("")
  const [organizationType, setOrganizationType] = useState("")
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [unlinkingId, setUnlinkingId] = useState<number | null>(null)
  const [moveSubstrate, setMoveSubstrate] = useState<LinkedOrganizationSubstrateItem | null>(null)

  const canonicalListHref = useMemo(() => {
    const base = `${catalogBasePath}/organizations/canonical`
    const qs = searchParams.toString()
    if (qs) return `${base}?${qs}`
    return filterScopeSuffix ? `${base}${filterScopeSuffix}` : base
  }, [catalogBasePath, searchParams, filterScopeSuffix])

  const orderedTypeOptions = useMemo(
    () => organizationTypeManualSelectOptions(organizationType),
    [organizationType],
  )

  const loadOrganization = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false): Promise<boolean> => {
      try {
        if (!quiet) setLoading(true)
        const row = await getCanonicalOrganization(
          canonicalId,
          sbSlug,
          evidenceProjectSlug || undefined,
        )
        setOrganization(row)
        setLabel(row.label)
        setOrganizationType(row.organization_type ?? "")
        return true
      } catch (e) {
        if (isStylebookApiNotFoundError(e)) {
          setOrganization(null)
          return false
        }
        console.error(e)
        if (!quiet) setOrganization(null)
        return false
      } finally {
        if (!quiet) setLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  const loadSubstrates = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setSubstratesLoading(true)
      try {
        const r = await listCanonicalLinkedOrganizationSubstrates(
          canonicalId,
          sbSlug,
          evidenceProjectSlug || undefined,
        )
        setSubstrates(r.substrates)
      } catch {
        setSubstrates([])
      } finally {
        if (!quiet) setSubstratesLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  const loadMentions = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setMentionsLoading(true)
      try {
        const m = await getCanonicalOrganizationMentions(
          canonicalId,
          sbSlug,
          500,
          0,
          undefined,
          "desc",
          evidenceProjectSlug || undefined,
        )
        setMentions(m.mentions)
      } catch {
        setMentions([])
      } finally {
        if (!quiet) setMentionsLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  const refreshCanonicalPage = useCallback(
    async (quiet = false) => {
      if (!id || !stylebookSlug || deleting) return
      const found = await loadOrganization(id, stylebookSlug, true)
      if (!found) {
        setSubstrates([])
        setMentions([])
        return
      }
      await loadSubstrates(id, stylebookSlug, quiet)
      await loadMentions(id, stylebookSlug, quiet)
    },
    [id, stylebookSlug, deleting, loadOrganization, loadSubstrates, loadMentions],
  )

  useEffect(() => {
    if (!id || !stylebookSlug || deleting) return
    void loadOrganization(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, loadOrganization])

  useEffect(() => {
    if (!id || !stylebookSlug || deleting || organization?.id !== id) return
    void loadSubstrates(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, organization, loadSubstrates])

  useEffect(() => {
    if (!id || !stylebookSlug || deleting || organization?.id !== id) return
    void loadMentions(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, organization, loadMentions])

  const tableLoading = substratesLoading || mentionsLoading

  async function handleUnlinkSubstrate(sub: LinkedOrganizationSubstrateItem) {
    if (!sub.project_slug) {
      showError("Missing project for this linked organization.")
      return
    }
    setUnlinkingId(sub.id)
    try {
      await unlinkOrganizationSubstrateFromCanonical(sub.id, sub.project_slug)
      await refreshCanonicalPage(true)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Unlink failed")
    } finally {
      setUnlinkingId(null)
    }
  }

  async function handleSave() {
    if (!organization || !stylebookSlug) return
    const trimmedLabel = label.trim()
    if (!trimmedLabel) {
      showError("Name is required")
      return
    }
    setSaving(true)
    try {
      await patchCanonicalOrganization(
        organization.id,
        stylebookSlug,
        {
          label: trimmedLabel,
          organization_type: organizationType.trim() || null,
        },
        evidenceProjectSlug || undefined,
      )
      setEditing(false)
      await refreshCanonicalPage(true)
    } catch (e) {
      console.error(e)
      showError("Failed to save organization")
    } finally {
      setSaving(false)
    }
  }

  function resetEditFieldsFromOrganization(row: CanonicalOrganization) {
    setLabel(row.label)
    setOrganizationType(row.organization_type ?? "")
  }

  const onDelete = useCallback(async () => {
    if (!id || !stylebookSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalOrganization(id, stylebookSlug)
      navigate(canonicalListHref)
    } catch (e) {
      if (isStylebookApiNotFoundError(e)) {
        navigate(canonicalListHref)
        return
      }
      console.error(e)
      showError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }, [id, stylebookSlug, navigate, canonicalListHref, showError])

  usePromptDeleteEmptyCanonical({
    canonicalKey: `${stylebookSlug}:${evidenceProjectSlug}:${id ?? ""}`,
    enabled: Boolean(id && !deleting),
    mentions,
    mentionsLoading,
    substrates,
    substratesLoading,
    showConfirm,
    onDelete,
  })

  const notFound = !loading && !organization ? (
    <div className="container mx-auto p-6">
      <p className="text-muted-foreground">Organization not found.</p>
      <Button variant="outline" className="mt-4" asChild>
        <Link to={canonicalListHref}>Back to organizations</Link>
      </Button>
    </div>
  ) : undefined

  return (
    <CanonicalDetailLayout
      config={organizationCanonicalDetailConfig}
      loading={loading}
      notFound={notFound}
      breadcrumbs={[
        { label: crumbRoot.label, to: crumbRoot.to },
        { label: organizationCanonicalDetailConfig.listBreadcrumbLabel, to: canonicalListHref },
        { label: organization?.label ?? "" },
      ]}
      title={organization?.label ?? ""}
      editing={editing}
      saving={saving}
      canEdit={canEdit}
      onStartEdit={() => {
        if (organization) resetEditFieldsFromOrganization(organization)
        setEditing(true)
      }}
      onCancelEdit={() => {
        if (organization) resetEditFieldsFromOrganization(organization)
        setEditing(false)
      }}
      onSave={() => void handleSave()}
      onDeleteClick={() => setDeleteOpen(true)}
      deleteOpen={deleteOpen}
      onDeleteOpenChange={(open) => !deleting && setDeleteOpen(open)}
      deleting={deleting}
      onDelete={onDelete}
      stylebookSlug={stylebookSlug}
      entityId={organization?.id}
      entityDisplayName={organization?.label}
      details={
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {editing ? (
              <>
                <div className="space-y-1">
                  <Label htmlFor="organization-label" className="text-xs font-medium">
                    Name
                  </Label>
                  <Input
                    id="organization-label"
                    className="h-8 text-xs"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    disabled={!canEdit || saving}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="organization-type" className="text-xs font-medium">
                    Type
                  </Label>
                  <Select
                    value={organizationType || "none"}
                    onValueChange={(v) => setOrganizationType(v === "none" ? "" : v)}
                    disabled={!canEdit || saving}
                  >
                    <SelectTrigger id="organization-type" className="h-8 text-xs">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      {orderedTypeOptions.map((t) => (
                        <SelectItem key={t} value={t}>
                          {placeExtractTypeLabel(t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            ) : (
              <>
                <div>
                  <span className="text-muted-foreground">Name:</span> {organization?.label}
                </div>
                {organization?.organization_type ? (
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    {placeExtractTypeLabel(organization.organization_type)}
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      }
      mentions={{
        substrates,
        mentions,
        loading: tableLoading,
        unlinkingId,
        onUnlink: (s) => void handleUnlinkSubstrate(s),
        onMove: setMoveSubstrate,
      }}
      meta={
        organization && stylebookSlug ? (
          <OrganizationMetaTab
            organizationId={organization.id}
            stylebookSlug={stylebookSlug}
            onMetaUpdated={() => void loadOrganization(organization.id, stylebookSlug, true)}
          />
        ) : null
      }
    >
      {moveSubstrate ? (
        <OrganizationCanonicalLinkModal
          open={moveSubstrate !== null}
          onOpenChange={(o) => {
            if (!o) setMoveSubstrate(null)
          }}
          projectSlug={moveSubstrate.project_slug}
          stylebookSlug={stylebookSlug}
          substrateOrganizationId={moveSubstrate.id}
          excludeCanonicalId={organization?.id ?? ""}
          title="Move linked organization to another canonical"
          onDone={() => void refreshCanonicalPage(true)}
        />
      ) : null}
    </CanonicalDetailLayout>
  )
}
