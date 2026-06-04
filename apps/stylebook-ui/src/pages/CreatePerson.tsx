import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import {
  CreateCanonicalShell,
  createCanonicalFormClasses,
} from "@/components/CreateCanonicalShell"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { createCanonicalPerson } from "@/lib/api"
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
import { Switch } from "@/components/ui/switch"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import {
  PERSON_EXTRACT_PERSON_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import { derivePersonSortKeyFromLabel } from "@/lib/personSortKey"
import { Loader2 } from "lucide-react"

const CREATE_PERSON_TYPE_NONE = "__none__"

export default function CreatePerson() {
  const { showMessage, showError } = useAppMessage()
  const navigate = useNavigate()
  const { filterScopeSuffix, stylebookSlug, catalogBasePath, projectFilterSlug } =
    useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()

  const [label, setLabel] = useState("")
  const [title, setTitle] = useState("")
  const [affiliation, setAffiliation] = useState("")
  const [personType, setPersonType] = useState("")
  const [publicFigure, setPublicFigure] = useState(false)
  const [sortKey, setSortKey] = useState("")
  const [sortKeyEdited, setSortKeyEdited] = useState(false)
  const [creating, setCreating] = useState(false)

  const orderedTypeOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions([...PERSON_EXTRACT_PERSON_TYPES]),
    [],
  )

  const peopleListHref = `${catalogBasePath}/people/canonical${filterScopeSuffix}`

  const handleSubmit = async () => {
    if (!stylebookSlug) return
    const trimmedLabel = label.trim()
    if (!trimmedLabel) {
      showMessage("Please enter a name", { title: "Name required" })
      return
    }
    try {
      setCreating(true)
      const person = await createCanonicalPerson(
        stylebookSlug,
        {
          label: trimmedLabel,
          title: title.trim() || null,
          affiliation: affiliation.trim() || null,
          person_type: personType.trim() || null,
          public_figure: publicFigure,
          sort_key: sortKey.trim() || derivePersonSortKeyFromLabel(trimmedLabel),
        },
        projectFilterSlug || undefined,
      )
      navigate(`${catalogBasePath}/people/canonical/${person.id}${filterScopeSuffix}`)
    } catch (error) {
      console.error("Failed to create person:", error)
      showError(
        `Failed to create person: ${error instanceof Error ? error.message : "Unknown error"}`,
      )
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = () => {
    navigate(peopleListHref)
  }

  return (
    <CreateCanonicalShell
      breadcrumbs={[
        { label: crumbRoot.label, to: crumbRoot.to },
        { label: "People", to: peopleListHref },
        { label: "Create" },
      ]}
      title="Create Person"
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
              "Create Person"
            )}
          </Button>
        </>
      }
    >
      <div className={createCanonicalFormClasses.grid}>
        <div className={createCanonicalFormClasses.wideFormColumn}>
          <Card>
            <CardHeader>
              <CardTitle>Person Details</CardTitle>
              <CardDescription>Enter the basic information for this person</CardDescription>
            </CardHeader>
            <CardContent>
              <div className={createCanonicalFormClasses.fieldGrid}>
                <div className={createCanonicalFormClasses.fieldGridFull}>
                  <Label htmlFor="person-label">Name *</Label>
                  <Input
                    id="person-label"
                    value={label}
                    onChange={(e) => {
                      const next = e.target.value
                      setLabel(next)
                      if (!sortKeyEdited) {
                        setSortKey(derivePersonSortKeyFromLabel(next))
                      }
                    }}
                    placeholder="e.g., Jane Doe"
                    disabled={!canEdit || creating}
                  />
                </div>
                <div>
                  <Label htmlFor="person-title">Title</Label>
                  <Input
                    id="person-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g., Mayor"
                    disabled={!canEdit || creating}
                  />
                </div>
                <div>
                  <Label htmlFor="person-affiliation">Affiliation</Label>
                  <Input
                    id="person-affiliation"
                    value={affiliation}
                    onChange={(e) => setAffiliation(e.target.value)}
                    placeholder="e.g., City Hall"
                    disabled={!canEdit || creating}
                  />
                </div>
                <div>
                  <Label htmlFor="person-type">Type</Label>
                  <Select
                    value={personType || CREATE_PERSON_TYPE_NONE}
                    onValueChange={(v) =>
                      setPersonType(v === CREATE_PERSON_TYPE_NONE ? "" : v)
                    }
                    disabled={!canEdit || creating}
                  >
                    <SelectTrigger
                      id="person-type"
                      className={createCanonicalFormClasses.selectTrigger}
                    >
                      <SelectValue placeholder="Select type…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={CREATE_PERSON_TYPE_NONE}>None</SelectItem>
                      {orderedTypeOptions.map((t) => (
                        <SelectItem key={t} value={t}>
                          {placeExtractTypeLabel(t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="person-sort-key">Sort key</Label>
                  <Input
                    id="person-sort-key"
                    value={sortKey}
                    onChange={(e) => {
                      setSortKeyEdited(true)
                      setSortKey(e.target.value)
                    }}
                    placeholder="e.g., last name for list ordering"
                    disabled={!canEdit || creating}
                  />
                </div>
                <div className={`flex items-center gap-3 ${createCanonicalFormClasses.fieldGridFull}`}>
                  <Switch
                    id="person-public-figure"
                    checked={publicFigure}
                    onCheckedChange={setPublicFigure}
                    disabled={!canEdit || creating}
                  />
                  <Label htmlFor="person-public-figure">Public figure</Label>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </CreateCanonicalShell>
  )
}
