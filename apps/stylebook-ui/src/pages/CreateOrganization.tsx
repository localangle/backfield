import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import {
  CreateCanonicalShell,
  createCanonicalFormClasses,
} from "@/components/CreateCanonicalShell"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { createCanonicalOrganization } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import {
  ORGANIZATION_EXTRACT_ORGANIZATION_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import { Loader2 } from "lucide-react"

const CREATE_ORGANIZATION_TYPE_NONE = "__none__"

export default function CreateOrganization() {
  const { showMessage, showError } = useAppMessage()
  const navigate = useNavigate()
  const { filterScopeSuffix, stylebookSlug, catalogBasePath, projectFilterSlug } =
    useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()

  const [label, setLabel] = useState("")
  const [organizationType, setOrganizationType] = useState("")
  const [creating, setCreating] = useState(false)

  const orderedTypeOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions([...ORGANIZATION_EXTRACT_ORGANIZATION_TYPES]),
    [],
  )

  const organizationsListHref = `${catalogBasePath}/organizations/canonical${filterScopeSuffix}`

  const handleSubmit = async () => {
    if (!stylebookSlug) return
    const trimmedLabel = label.trim()
    if (!trimmedLabel) {
      showMessage("Please enter a name", { title: "Name required" })
      return
    }
    try {
      setCreating(true)
      const org = await createCanonicalOrganization(
        stylebookSlug,
        {
          label: trimmedLabel,
          organization_type: organizationType.trim() || null,
        },
        projectFilterSlug || undefined,
      )
      navigate(`${catalogBasePath}/organizations/canonical/${org.id}${filterScopeSuffix}`)
    } catch (error) {
      console.error("Failed to create organization:", error)
      showError(
        `Failed to create organization: ${error instanceof Error ? error.message : "Unknown error"}`,
      )
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = () => {
    navigate(organizationsListHref)
  }

  return (
    <CreateCanonicalShell
      breadcrumbs={[
        { label: crumbRoot.label, to: crumbRoot.to },
        { label: "Organizations", to: organizationsListHref },
        { label: "Create" },
      ]}
      title="Create Organization"
      footer={
        <>
          <Button variant="outline" onClick={handleCancel} disabled={creating}>
            Cancel
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={!canEdit || creating || !label.trim()}
          >
            {creating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              "Create Organization"
            )}
          </Button>
        </>
      }
    >
      <div className={createCanonicalFormClasses.grid}>
        <div className={createCanonicalFormClasses.wideFormColumn}>
          <Card>
            <CardHeader>
              <CardTitle>Organization Details</CardTitle>
              <CardDescription>Enter the basic information for this organization</CardDescription>
            </CardHeader>
            <CardContent>
              <div className={createCanonicalFormClasses.fieldGrid}>
                <div className={createCanonicalFormClasses.fieldGridFull}>
                  <Label htmlFor="organization-label">Name *</Label>
                  <Input
                    id="organization-label"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="e.g., Chicago Public Schools"
                    disabled={!canEdit || creating}
                  />
                </div>
                <div>
                  <Label htmlFor="organization-type">Type</Label>
                  <Select
                    value={organizationType || CREATE_ORGANIZATION_TYPE_NONE}
                    onValueChange={(v) =>
                      setOrganizationType(v === CREATE_ORGANIZATION_TYPE_NONE ? "" : v)
                    }
                    disabled={!canEdit || creating}
                  >
                    <SelectTrigger
                      id="organization-type"
                      className={createCanonicalFormClasses.selectTrigger}
                    >
                      <SelectValue placeholder="Select type…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={CREATE_ORGANIZATION_TYPE_NONE}>None</SelectItem>
                      {orderedTypeOptions.map((t) => (
                        <SelectItem key={t} value={t}>
                          {placeExtractTypeLabel(t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </CreateCanonicalShell>
  )
}
