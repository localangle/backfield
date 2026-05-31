import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { createCanonicalPerson, listCanonicalPersonTypes } from "@/lib/api"
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
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import { Loader2 } from "lucide-react"

function derivePersonSortKey(label: string, explicit?: string): string {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ")
  const fromExplicit = explicit != null ? normalize(explicit) : ""
  if (fromExplicit) return fromExplicit
  const parts = label.trim().split(/\s+/)
  if (parts.length >= 2) return normalize(parts[parts.length - 1]!)
  return normalize(parts[0] ?? "")
}

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
  const [types, setTypes] = useState<string[]>([])
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!stylebookSlug) return
    void (async () => {
      try {
        const res = await listCanonicalPersonTypes(stylebookSlug)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [stylebookSlug])

  const orderedTypeOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

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
          sort_key: sortKey.trim() || derivePersonSortKey(trimmedLabel),
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
    navigate(`${catalogBasePath}/people/canonical${filterScopeSuffix}`)
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <Breadcrumbs
          className="mb-3"
          items={[
            { label: crumbRoot.label, to: crumbRoot.to },
            {
              label: "People",
              to: `${catalogBasePath}/people/canonical${filterScopeSuffix}`,
            },
            { label: "Create" },
          ]}
        />
        <h1 className="text-3xl font-bold">Create person</h1>
      </div>

      <div className="max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle>Person details</CardTitle>
            <CardDescription>Enter the information for this person</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="person-label" className="text-xs font-medium">
                Name *
              </Label>
              <Input
                id="person-label"
                className="h-8 text-xs"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g., Jane Doe"
                disabled={!canEdit || creating}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="min-w-0 space-y-1">
                <Label htmlFor="person-title" className="text-xs font-medium">
                  Title
                </Label>
                <Input
                  id="person-title"
                  className="h-8 text-xs"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g., Mayor"
                  disabled={!canEdit || creating}
                />
              </div>
              <div className="min-w-0 space-y-1">
                <Label htmlFor="person-affiliation" className="text-xs font-medium">
                  Affiliation
                </Label>
                <Input
                  id="person-affiliation"
                  className="h-8 text-xs"
                  value={affiliation}
                  onChange={(e) => setAffiliation(e.target.value)}
                  placeholder="e.g., City Hall"
                  disabled={!canEdit || creating}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="person-type" className="text-xs font-medium">
                Type
              </Label>
              <Select
                value={personType || "none"}
                onValueChange={(v) => setPersonType(v === "none" ? "" : v)}
                disabled={!canEdit || creating}
              >
                <SelectTrigger id="person-type" className="h-8 text-xs">
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
            <div className="grid grid-cols-2 items-end gap-2">
              <div className="flex items-center gap-2 pb-1">
                <Label htmlFor="person-public-figure" className="shrink-0 text-xs font-medium">
                  Public figure
                </Label>
                <Switch
                  id="person-public-figure"
                  checked={publicFigure}
                  onCheckedChange={setPublicFigure}
                  disabled={!canEdit || creating}
                />
              </div>
              <div className="min-w-0 space-y-1">
                <Label htmlFor="person-sort-key" className="text-xs font-medium">
                  Sort key
                </Label>
                <Input
                  id="person-sort-key"
                  className="h-8 text-xs"
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value)}
                  placeholder="Last name"
                  disabled={!canEdit || creating}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 flex justify-end gap-2 max-w-2xl">
        <Button variant="outline" onClick={handleCancel} disabled={creating}>
          Cancel
        </Button>
        <Button onClick={() => void handleSubmit()} disabled={!canEdit || creating || !label.trim()}>
          {creating ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Creating…
            </>
          ) : (
            "Create person"
          )}
        </Button>
      </div>
    </div>
  )
}
