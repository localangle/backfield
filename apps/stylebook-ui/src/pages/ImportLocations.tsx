import { Fragment, useEffect, useMemo, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  analyzeImportGeoJson,
  importGeoJson,
  type AnalyzeGeoJsonResponse,
  type ImportGeoJsonMetaPropertyMapping,
  type ImportGeoJsonResponse,
} from "@/lib/api"
import { fetchPlaceExtractLocationTypes } from "@/lib/stylebook-api/taxonomy"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import {
  buildFeatureCollectionForImport,
  canProceedFromMapping,
  deriveImportRows,
  normalizeFeatureCollectionForImport,
  slugifyLocationTypeLabel,
  validateDerivedRows,
  type DerivedImportRow,
  type GeoJsonFeatureCollection,
  type GeoJsonFieldMappings,
  type ReviewEditsByFeatureIndex,
} from "@/lib/import/geojsonImport"
import { cn } from "@/lib/utils"
import { CheckCircle2, ChevronRight } from "lucide-react"

type WizardStep = "upload" | "mapping" | "metadata" | "review" | "importing" | "complete"

const MAX_GEOJSON_BYTES = 25 * 1024 * 1024

const WIZARD_STEP_ORDER: WizardStep[] = [
  "upload",
  "mapping",
  "metadata",
  "review",
  "importing",
  "complete",
]

const STEP_LABELS: Record<WizardStep, string> = {
  upload: "Upload",
  mapping: "Mapping",
  metadata: "Metadata",
  review: "Review",
  importing: "Importing",
  complete: "Complete",
}

type MetaMappingRow = { rowId: string; propertyKey: string; metaType: string }

function newMetaMappingRow(): MetaMappingRow {
  const rowId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `meta-row-${Date.now()}-${Math.random().toString(16).slice(2)}`
  return { rowId, propertyKey: "", metaType: "" }
}

function buildMetaPropertyMappingsForImport(rows: MetaMappingRow[]): ImportGeoJsonMetaPropertyMapping[] {
  const out: ImportGeoJsonMetaPropertyMapping[] = []
  for (const r of rows) {
    const pk = r.propertyKey.trim()
    const mt = r.metaType.trim()
    if (!pk || !mt) continue
    out.push({ property_key: pk, meta_type: mt })
  }
  return out
}

/** Radix Select value when no manual type is chosen */
const MANUAL_LOCATION_TYPE_NONE = "__none__"
/** Manual type: Custom + — enter a label → slug (not from the taxonomy list). */
const MANUAL_LOCATION_TYPE_OTHER = "__other__"

function formatPropertyExample(v: unknown): string | null {
  if (v == null) return null
  let s: string
  if (typeof v === "string") s = v
  else if (typeof v === "number" || typeof v === "boolean") s = String(v)
  else {
    try {
      s = JSON.stringify(v)
    } catch {
      s = String(v)
    }
  }
  s = s.replace(/\s+/g, " ").trim()
  if (!s) return null
  const MAX = 48
  if (s.length > MAX) return `${s.slice(0, MAX - 1)}…`
  return s
}

export default function ImportLocations() {
  const [searchParams] = useSearchParams()
  const { filterScopeSuffix, stylebookSlug } = useProjectCatalogScope()
  const { showError } = useAppMessage()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()
  const [step, setStep] = useState<WizardStep>("upload")
  const [geojsonText, setGeojsonText] = useState<string>("")
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [geojsonTooLarge, setGeojsonTooLarge] = useState(false)
  const [parsedGeojson, setParsedGeojson] = useState<Record<string, unknown> | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeGeoJsonResponse | null>(null)
  const [mappings, setMappings] = useState<GeoJsonFieldMappings>({
    labelProperty: null,
    formattedAddressProperty: null,
    locationTypeProperty: null,
    locationTypeValue: null,
  })
  const [derivedRows, setDerivedRows] = useState<DerivedImportRow[] | null>(null)
  const [reviewEdits, setReviewEdits] = useState<ReviewEditsByFeatureIndex>({})
  const [excluded, setExcluded] = useState<Set<number>>(() => new Set())
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportGeoJsonResponse | null>(null)
  const [metaMappingRows, setMetaMappingRows] = useState<MetaMappingRow[]>([])
  const [locationTypeMode, setLocationTypeMode] = useState<"manual" | "geojson">("manual")
  const [manualLocationTypeLabel, setManualLocationTypeLabel] = useState("")
  const [placeExtractTypesList, setPlaceExtractTypesList] = useState<string[]>(() => [
    ...PLACE_EXTRACT_LOCATION_TYPES,
  ])
  const [manualLocationSelect, setManualLocationSelect] = useState<string>(
    MANUAL_LOCATION_TYPE_NONE,
  )
  const prevWizardStepRef = useRef<WizardStep>(step)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await fetchPlaceExtractLocationTypes()
        if (!cancelled && Array.isArray(res.types) && res.types.length > 0) {
          setPlaceExtractTypesList(res.types)
        }
      } catch {
        // Keep bundled ``PLACE_EXTRACT_LOCATION_TYPES`` fallback.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const enteredMapping =
      step === "mapping" && prevWizardStepRef.current !== "mapping"
    prevWizardStepRef.current = step
    if (!enteredMapping || locationTypeMode !== "manual") return

    // Sync manual type UI from ``mappings`` only when entering Mapping (not on each keystroke).
    const v = (mappings.locationTypeValue ?? "").trim()
    const presets = new Set(placeExtractTypesList)
    if (!v) {
      setManualLocationSelect(MANUAL_LOCATION_TYPE_NONE)
      setManualLocationTypeLabel("")
      return
    }
    if (presets.has(v)) {
      setManualLocationSelect(v)
      setManualLocationTypeLabel("")
      return
    }
    setManualLocationSelect(MANUAL_LOCATION_TYPE_OTHER)
    setManualLocationTypeLabel(v.replace(/_/g, " "))
  }, [step, locationTypeMode, placeExtractTypesList])

  useEffect(() => {
    setStep("upload")
    setGeojsonText("")
    setUploadedFileName(null)
    setGeojsonTooLarge(false)
    setParsedGeojson(null)
    setAnalyzeResult(null)
    setMappings({
      labelProperty: null,
      formattedAddressProperty: null,
      locationTypeProperty: null,
      locationTypeValue: null,
    })
    setDerivedRows(null)
    setReviewEdits({})
    setExcluded(new Set())
    setImporting(false)
    setImportResult(null)
    setMetaMappingRows([])
    setLocationTypeMode("manual")
    setManualLocationTypeLabel("")
    setPlaceExtractTypesList([...PLACE_EXTRACT_LOCATION_TYPES])
    setManualLocationSelect(MANUAL_LOCATION_TYPE_NONE)
  }, [stylebookSlug])

  const backHref = useMemo(
    () => `/locations/canonical${filterScopeSuffix}`,
    [filterScopeSuffix],
  )

  const validateAndSetGeojson = (text: string): boolean => {
    const trimmed = text.trim()
    if (!trimmed) {
      setParsedGeojson(null)
      setGeojsonTooLarge(false)
      return false
    }
    const byteSize = new Blob([text]).size
    if (byteSize > MAX_GEOJSON_BYTES) {
      setParsedGeojson(null)
      setGeojsonTooLarge(true)
      showError("GeoJSON exceeds 25MB. Please split it into smaller files.")
      return false
    }
    setGeojsonTooLarge(false)
    let obj: unknown
    try {
      obj = JSON.parse(trimmed)
    } catch (e) {
      setParsedGeojson(null)
      showError("GeoJSON is not valid JSON.")
      return false
    }
    if (!obj || typeof obj !== "object") {
      setParsedGeojson(null)
      showError("GeoJSON must be an object.")
      return false
    }
    const o = obj as Record<string, unknown>
    if (o.type !== "FeatureCollection" || !Array.isArray(o.features)) {
      setParsedGeojson(null)
      showError("GeoJSON must be a FeatureCollection with a features array.")
      return false
    }
    const normalized = normalizeFeatureCollectionForImport(o as GeoJsonFeatureCollection)
    setParsedGeojson(normalized as unknown as Record<string, unknown>)
    return true
  }

  const canValidate = Boolean(
    canEdit && stylebookSlug && parsedGeojson && step === "upload" && !analyzing,
  )

  const clearUploadedGeoJson = () => {
    setGeojsonText("")
    setUploadedFileName(null)
    setParsedGeojson(null)
    setAnalyzeResult(null)
  }
  const availableProperties = analyzeResult?.available_properties ?? []
  const sampleProperties = analyzeResult?.sample_feature?.properties ?? null

  const fc = parsedGeojson as GeoJsonFeatureCollection | null
  const rowsForValidation = useMemo(() => {
    if (!fc || !analyzeResult) return null
    return deriveImportRows(fc, mappings)
  }, [analyzeResult, fc, mappings])
  const validationSummary = useMemo(() => {
    if (!rowsForValidation) return null
    return validateDerivedRows(rowsForValidation)
  }, [rowsForValidation])
  const canProceed = Boolean(validationSummary && canProceedFromMapping(validationSummary))
  const importPayload = useMemo(() => {
    if (!fc || !derivedRows) return null
    return buildFeatureCollectionForImport(fc, mappings, reviewEdits, excluded)
  }, [excluded, fc, derivedRows, mappings, reviewEdits])

  const sortedManualLocationTypes = useMemo(
    () => sortReviewQueueTypeFilterOptions([...placeExtractTypesList]),
    [placeExtractTypesList],
  )

  const handleManualLocationTypeSelect = (value: string) => {
    setManualLocationSelect(value)
    if (value === MANUAL_LOCATION_TYPE_NONE) {
      setManualLocationTypeLabel("")
      setMappings((prev) => ({
        ...prev,
        locationTypeValue: null,
        locationTypeProperty: null,
      }))
      return
    }
    if (value === MANUAL_LOCATION_TYPE_OTHER) {
      setManualLocationTypeLabel("")
      setMappings((prev) => ({
        ...prev,
        locationTypeValue: null,
        locationTypeProperty: null,
      }))
      return
    }
    setManualLocationTypeLabel("")
    setMappings((prev) => ({
      ...prev,
      locationTypeValue: value,
      locationTypeProperty: null,
    }))
  }

  const manualStoredSlugPreview =
    manualLocationSelect === MANUAL_LOCATION_TYPE_OTHER
      ? slugifyLocationTypeLabel(manualLocationTypeLabel)
      : (mappings.locationTypeValue ?? "").trim()

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "Import" },
            ]}
          />
          <h1 className="text-3xl font-bold">Import locations (GeoJSON)</h1>
        </div>
        <Link to={backHref}>
          <Button variant="outline">Back to canonicals</Button>
        </Link>
      </div>

      <nav
        aria-label="Import steps"
        className="flex flex-wrap items-center gap-x-0 gap-y-1 border-b border-border/60 pb-4 text-sm"
      >
        {WIZARD_STEP_ORDER.map((s, i) => (
          <Fragment key={s}>
            {i > 0 ? (
              <ChevronRight
                aria-hidden
                className="mx-1 h-3.5 w-3.5 shrink-0 text-muted-foreground/35"
              />
            ) : null}
            <button
              type="button"
              onClick={() => setStep(s)}
              aria-current={s === step ? "step" : undefined}
              className={cn(
                "rounded-sm px-1 py-0.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                s === step
                  ? "font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground/85",
              )}
            >
              {STEP_LABELS[s]}
            </button>
          </Fragment>
        ))}
      </nav>

      {step === "upload" ? (
        <Card>
          <CardHeader>
            <CardTitle>Upload or paste GeoJSON</CardTitle>
            <CardDescription>
              Upload a file or paste GeoJSON directly.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Choose GeoJSON file</Label>
              <Input
                type="file"
                accept=".geojson,.json,application/geo+json,application/json"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  if (f.size > MAX_GEOJSON_BYTES) {
                    setGeojsonText("")
                    setUploadedFileName(null)
                    setParsedGeojson(null)
                    setAnalyzeResult(null)
                    setGeojsonTooLarge(true)
                    showError("GeoJSON file exceeds 25MB. Please split it into smaller files.")
                    return
                  }
                  setUploadedFileName(f.name)
                  void (async () => {
                    const text = await f.text()
                    setGeojsonText(text)
                    setAnalyzeResult(null)
                    validateAndSetGeojson(text)
                  })()
                }}
              />
              <p className="text-xs text-muted-foreground">Max file size: 25MB.</p>
            </div>

            {uploadedFileName ? (
              <div className="flex items-center justify-between gap-3 rounded border bg-muted/30 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <span className="text-muted-foreground">Using uploaded file:</span>{" "}
                  <span className="font-medium truncate">{uploadedFileName}</span>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setUploadedFileName(null)
                    setGeojsonText("")
                    setParsedGeojson(null)
                    setAnalyzeResult(null)
                  }}
                >
                  Paste instead
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Label>Or paste GeoJSON</Label>
                <Textarea
                  value={geojsonText}
                  onChange={(e) => {
                    const t = e.target.value
                    setUploadedFileName(null)
                    setGeojsonText(t)
                    setAnalyzeResult(null)
                    // Validate only on non-empty to avoid spamming dialogs while typing.
                    if (t.trim().length > 0) validateAndSetGeojson(t)
                    else setParsedGeojson(null)
                  }}
                  placeholder='{"type":"FeatureCollection","features":[...]}'
                  className="min-h-[12rem] font-mono text-xs"
                />
                {geojsonTooLarge ? (
                  <div className="text-sm text-destructive">GeoJSON exceeds 25MB.</div>
                ) : null}
              </div>
            )}

            {!analyzeResult ? (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  disabled={!canValidate}
                  onClick={async () => {
                    if (!stylebookSlug || !parsedGeojson) return
                    setAnalyzing(true)
                    try {
                      const res = await analyzeImportGeoJson(stylebookSlug, parsedGeojson)
                      setAnalyzeResult(res)
                    } catch (e) {
                      console.error(e)
                      showError(e instanceof Error ? e.message : "Validation failed")
                    } finally {
                      setAnalyzing(false)
                    }
                  }}
                >
                  {analyzing ? "Validating…" : "Validate"}
                </Button>
                <Button type="button" variant="outline" onClick={clearUploadedGeoJson}>
                  Clear
                </Button>
              </div>
            ) : null}

            {analyzeResult ? (
              <div className="space-y-2 pt-2">
                <div className="rounded border bg-muted/40 p-3 text-sm">
                  <div className="flex items-start gap-2">
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 shrink-0 text-green-600"
                      aria-hidden
                      strokeWidth={2}
                    />
                    <div className="min-w-0 flex-1 space-y-2">
                      <div>
                        Features:{" "}
                        <span className="font-medium">{analyzeResult.feature_count}</span>
                      </div>
                      <div>
                        <div className="text-sm">
                          Available properties ({analyzeResult.available_properties.length}):
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {analyzeResult.available_properties.map((p) => (
                            <span
                              key={p}
                              className="rounded border bg-muted px-2 py-1 text-xs text-muted-foreground"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <Button type="button" variant="outline" onClick={clearUploadedGeoJson}>
                    Clear
                  </Button>
                  <Button
                    type="button"
                    disabled={!parsedGeojson || !stylebookSlug}
                    onClick={() => setStep("mapping")}
                  >
                    Continue to mapping
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {step === "mapping" ? (
        <Card>
          <CardHeader>
            <CardTitle>Mapping</CardTitle>
            <CardDescription>
              Map the canonical label and location type. Formatted address is read from the property
              you choose below; leave it unset to use the{" "}
              <span className="font-mono text-xs">formatted_address</span> field on each feature.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-6">
              <div className="space-y-2">
                <Label>Label / name property</Label>
                <Select
                  value={mappings.labelProperty ?? "__none__"}
                  onValueChange={(v) =>
                    setMappings((prev) => ({
                      ...prev,
                      labelProperty: v === "__none__" ? null : v,
                    }))
                  }
                >
                  <SelectTrigger className="h-10 w-full max-w-xl">
                    <SelectValue placeholder="Select property…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">None</SelectItem>
                    {availableProperties.map((p) => (
                      <SelectItem key={p} value={p}>
                        <div className="flex w-full items-center justify-between gap-3">
                          <span className="truncate">{p}</span>
                          {sampleProperties ? (
                            <span className="max-w-[18rem] truncate text-muted-foreground">
                              {formatPropertyExample(sampleProperties[p]) ?? "—"}
                            </span>
                          ) : null}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Formatted address property</Label>
                <p className="text-xs text-muted-foreground max-w-xl">
                  Canonical name comes from the label mapping only. This property fills formatted
                  address only.
                </p>
                <Select
                  value={mappings.formattedAddressProperty ?? "__default__"}
                  onValueChange={(v) =>
                    setMappings((prev) => ({
                      ...prev,
                      formattedAddressProperty: v === "__default__" ? null : v,
                    }))
                  }
                >
                  <SelectTrigger className="h-10 w-full max-w-xl">
                    <SelectValue placeholder="Default: formatted_address" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__default__">Default: formatted_address property</SelectItem>
                    {availableProperties.map((p) => (
                      <SelectItem key={p} value={p}>
                        <div className="flex w-full items-center justify-between gap-3">
                          <span className="truncate">{p}</span>
                          {sampleProperties ? (
                            <span className="max-w-[18rem] truncate text-muted-foreground">
                              {formatPropertyExample(sampleProperties[p]) ?? "—"}
                            </span>
                          ) : null}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2 max-w-xl">
                <Label>Location type</Label>
                {locationTypeMode === "manual" ? (
                  <>
                    <div className="space-y-3">
                      <Select
                        value={manualLocationSelect}
                        onValueChange={handleManualLocationTypeSelect}
                      >
                        <SelectTrigger className="h-10 w-full max-w-xl">
                          <SelectValue placeholder="Select location type…" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={MANUAL_LOCATION_TYPE_NONE}>None</SelectItem>
                          {sortedManualLocationTypes.map((slug) => (
                            <SelectItem key={slug} value={slug}>
                              {placeExtractTypeLabel(slug)}
                            </SelectItem>
                          ))}
                          <SelectItem value={MANUAL_LOCATION_TYPE_OTHER}>Custom +</SelectItem>
                        </SelectContent>
                      </Select>

                      {manualLocationSelect === MANUAL_LOCATION_TYPE_OTHER ? (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-start sm:max-w-xl">
                          <div className="min-w-0 space-y-1.5">
                            <span className="text-xs text-muted-foreground">Label</span>
                            <Input
                              value={manualLocationTypeLabel}
                              placeholder="e.g. Congressional District"
                              className="h-10 font-normal"
                              onChange={(e) => {
                                const next = e.target.value
                                setManualLocationTypeLabel(next)
                                const slug = slugifyLocationTypeLabel(next)
                                setMappings((prev) => ({
                                  ...prev,
                                  locationTypeValue: slug || null,
                                  locationTypeProperty: null,
                                }))
                              }}
                            />
                          </div>
                          <div className="min-w-0 space-y-1.5">
                            <span className="text-xs text-muted-foreground">Stored as (slug)</span>
                            <Input
                              readOnly
                              tabIndex={-1}
                              value={manualStoredSlugPreview}
                              placeholder="custom_type"
                              className="h-10 font-mono text-sm bg-muted/40"
                            />
                          </div>
                        </div>
                      ) : manualLocationSelect !== MANUAL_LOCATION_TYPE_NONE ? (
                        <div className="max-w-xl space-y-1.5">
                          <span className="text-xs text-muted-foreground">Stored as (slug)</span>
                          <Input
                            readOnly
                            tabIndex={-1}
                            value={manualStoredSlugPreview}
                            className="h-10 font-mono text-sm bg-muted/40"
                          />
                        </div>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      <button
                        type="button"
                        className="underline-offset-4 hover:underline"
                        onClick={() => {
                          setLocationTypeMode("geojson")
                          setManualLocationTypeLabel("")
                          setManualLocationSelect(MANUAL_LOCATION_TYPE_NONE)
                          setMappings((prev) => ({
                            ...prev,
                            locationTypeValue: null,
                          }))
                        }}
                      >
                        Import from GeoJSON
                      </button>
                      <span className="text-muted-foreground/80">
                        {" "}
                        — map type from a property on each feature instead.
                      </span>
                    </p>
                  </>
                ) : (
                  <>
                    <Select
                      value={mappings.locationTypeProperty ?? "__none__"}
                      onValueChange={(v) =>
                        setMappings((prev) => ({
                          ...prev,
                          locationTypeProperty: v === "__none__" ? null : v,
                          locationTypeValue: null,
                        }))
                      }
                    >
                      <SelectTrigger className="h-10 w-full">
                        <SelectValue placeholder="Select property…" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">None</SelectItem>
                        {availableProperties.map((p) => (
                          <SelectItem key={p} value={p}>
                            <div className="flex w-full items-center justify-between gap-3">
                              <span className="truncate">{p}</span>
                              {sampleProperties ? (
                                <span className="max-w-[18rem] truncate text-muted-foreground">
                                  {formatPropertyExample(sampleProperties[p]) ?? "—"}
                                </span>
                              ) : null}
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      <button
                        type="button"
                        className="underline-offset-4 hover:underline"
                        onClick={() => {
                          setLocationTypeMode("manual")
                          setManualLocationSelect(MANUAL_LOCATION_TYPE_NONE)
                          setManualLocationTypeLabel("")
                          setMappings((prev) => ({
                            ...prev,
                            locationTypeProperty: null,
                          }))
                        }}
                      >
                        Use manual type instead
                      </button>
                    </p>
                  </>
                )}
              </div>
            </div>

            {validationSummary ? (
              <div className="rounded border bg-muted/40 p-3 text-sm">
                <div className="flex items-start gap-2">
                  {canProceed && rowsForValidation ? (
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 shrink-0 text-green-600"
                      aria-hidden
                      strokeWidth={2}
                    />
                  ) : null}
                  <div className="min-w-0 flex-1">
                    <div>
                      Rows: <span className="font-medium">{validationSummary.total_rows}</span>
                    </div>
                    <div className="mt-1 text-muted-foreground">
                      Missing label: {validationSummary.missing_label_count} • Missing type:{" "}
                      {validationSummary.missing_location_type_count} • Missing geometry:{" "}
                      {validationSummary.missing_geometry_count}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Validate a FeatureCollection first.</div>
            )}

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep("upload")}
              >
                Back
              </Button>
              <Button
                type="button"
                disabled={!canProceed || !rowsForValidation}
                onClick={() => {
                  if (!rowsForValidation || !validationSummary) return
                  if (!canProceedFromMapping(validationSummary)) {
                    showError("Fix missing required fields before continuing.")
                    return
                  }
                  setDerivedRows(rowsForValidation)
                  setStep("metadata")
                }}
              >
                Next: Metadata
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "metadata" ? (
        <Card>
          <CardHeader>
            <CardTitle>Metadata (optional)</CardTitle>
            <CardDescription>
              Map GeoJSON property values onto canonical metadata types. Skip this step if you do
              not need extra fields on imported locations.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {availableProperties.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No feature properties were detected. You can skip this step.
              </p>
            ) : (
              <div className="space-y-3">
                <div className="rounded border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  Each row adds one metadata entry per imported location when that property has a
                  non-empty value. Values are stored under the property name as a key (so the
                  canonical detail view can show a Key / Value table).
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[42%]">GeoJSON property</TableHead>
                      <TableHead className="w-[42%]">Meta type</TableHead>
                      <TableHead className="w-24 text-right"> </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {metaMappingRows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-sm text-muted-foreground">
                          No mappings yet. Use &quot;Add mapping&quot; or skip.
                        </TableCell>
                      </TableRow>
                    ) : (
                      metaMappingRows.map((row) => (
                        <TableRow key={row.rowId}>
                          <TableCell>
                            <Select
                              value={row.propertyKey || "__none__"}
                              onValueChange={(v) =>
                                setMetaMappingRows((prev) =>
                                  prev.map((r) =>
                                    r.rowId === row.rowId
                                      ? { ...r, propertyKey: v === "__none__" ? "" : v }
                                      : r,
                                  ),
                                )
                              }
                            >
                              <SelectTrigger className="h-9">
                                <SelectValue placeholder="Property…" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="__none__">Select property…</SelectItem>
                                {availableProperties.map((p) => (
                                  <SelectItem key={p} value={p}>
                                    {p}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </TableCell>
                          <TableCell>
                            <Input
                              className="h-9"
                              placeholder="e.g. source_id"
                              value={row.metaType}
                              onChange={(e) =>
                                setMetaMappingRows((prev) =>
                                  prev.map((r) =>
                                    r.rowId === row.rowId ? { ...r, metaType: e.target.value } : r,
                                  ),
                                )
                              }
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setMetaMappingRows((prev) => prev.filter((r) => r.rowId !== row.rowId))
                              }
                            >
                              Remove
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={availableProperties.length === 0}
                  onClick={() => setMetaMappingRows((prev) => [...prev, newMetaMappingRow()])}
                >
                  Add mapping
                </Button>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setDerivedRows(null)
                  setStep("mapping")
                }}
              >
                Back
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setMetaMappingRows([])
                  setStep("review")
                }}
              >
                Skip
              </Button>
              <Button type="button" onClick={() => setStep("review")}>
                Next: Review
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "review" ? (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
            <CardDescription>Edit values and exclude rows before importing.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!derivedRows ? (
              <div className="text-sm text-muted-foreground">No derived rows yet.</div>
            ) : (
              <>
                <div className="text-sm text-muted-foreground">
                  Rows: <span className="font-medium text-foreground">{derivedRows.length}</span> • Excluded:{" "}
                  <span className="font-medium text-foreground">{excluded.size}</span>
                </div>

                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12">Skip</TableHead>
                      <TableHead className="w-16">#</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead className="w-48">Type</TableHead>
                      <TableHead>Formatted address</TableHead>
                      <TableHead className="w-36">Geometry</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {derivedRows.map((r) => {
                      const i = r.feature_index
                      const isExcluded = excluded.has(i)
                      const edits = reviewEdits[i] || {}
                      const label = edits.label ?? r.label ?? ""
                      const locType = edits.location_type ?? r.location_type ?? ""
                      const addr = edits.formatted_address ?? r.formatted_address ?? ""
                      return (
                        <TableRow key={i} className={isExcluded ? "opacity-50" : undefined}>
                          <TableCell>
                            <Checkbox
                              checked={isExcluded}
                              onCheckedChange={(checked) => {
                                setExcluded((prev) => {
                                  const next = new Set(prev)
                                  if (checked) next.add(i)
                                  else next.delete(i)
                                  return next
                                })
                              }}
                              aria-label={`Exclude row ${i}`}
                            />
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">{i + 1}</TableCell>
                          <TableCell>
                            <Input
                              value={label}
                              disabled={isExcluded}
                              onChange={(e) => {
                                const v = e.target.value
                                setReviewEdits((prev) => ({
                                  ...prev,
                                  [i]: { ...prev[i], label: v },
                                }))
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={locType}
                              disabled={isExcluded}
                              onChange={(e) => {
                                const v = e.target.value
                                setReviewEdits((prev) => ({
                                  ...prev,
                                  [i]: { ...prev[i], location_type: v },
                                }))
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={addr}
                              disabled={isExcluded}
                              onChange={(e) => {
                                const v = e.target.value
                                setReviewEdits((prev) => ({
                                  ...prev,
                                  [i]: { ...prev[i], formatted_address: v },
                                }))
                              }}
                            />
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {r.has_geometry ? (r.geometry_type ?? "—") : "Missing"}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </>
            )}
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={() => setStep("metadata")}>
                Back
              </Button>
              <Button
                type="button"
                disabled={
                  !canEdit ||
                  !stylebookSlug ||
                  !importPayload ||
                  importPayload.features.length === 0 ||
                  importing
                }
                onClick={async () => {
                  if (!stylebookSlug || !importPayload) return
                  setImporting(true)
                  setStep("importing")
                  try {
                    const metaPayload = buildMetaPropertyMappingsForImport(metaMappingRows)
                    const res = await importGeoJson(
                      stylebookSlug,
                      importPayload,
                      {
                        label_property: mappings.labelProperty ?? null,
                        location_type_property: mappings.locationTypeProperty ?? null,
                        formatted_address_property: mappings.formattedAddressProperty ?? null,
                        location_type_value: mappings.locationTypeValue ?? null,
                      },
                      metaPayload,
                    )
                    setImportResult(res)
                    setStep("complete")
                  } catch (e) {
                    setStep("review")
                    showError("Import failed. See console/network logs for details.")
                  } finally {
                    setImporting(false)
                  }
                }}
              >
                Import
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "importing" ? (
        <Card>
          <CardHeader>
            <CardTitle>Importing</CardTitle>
            <CardDescription>Creating canonicals…</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">This may take a moment for large files.</div>
          </CardContent>
        </Card>
      ) : null}

      {step === "complete" ? (
        <Card>
          <CardHeader>
            <CardTitle>Complete</CardTitle>
            <CardDescription>Import results</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {importResult ? (
              <>
                <div className="text-sm">
                  Created: <span className="font-medium">{importResult.created_count}</span> • Failed:{" "}
                  <span className="font-medium">{importResult.failed_count}</span> • Total:{" "}
                  <span className="font-medium">{importResult.total_features}</span>
                </div>

                {importResult.created.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Imported locations</div>
                    <ul className="max-h-[min(24rem,50vh)] divide-y divide-border overflow-y-auto rounded border bg-muted/40 text-sm">
                      {[...importResult.created]
                        .sort((a, b) => a.feature_index - b.feature_index)
                        .map((row) => (
                          <li
                            key={`${row.feature_index}-${row.canonical_id}`}
                            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2"
                          >
                            <span className="shrink-0 tabular-nums text-muted-foreground">
                              #{row.feature_index + 1}
                            </span>
                            <Link
                              className="break-words font-medium text-primary underline-offset-4 hover:underline"
                              target="_blank"
                              rel="noopener noreferrer"
                              to={`/locations/canonical/${encodeURIComponent(row.canonical_id)}${filterScopeSuffix}`}
                            >
                              {(row.label ?? "").trim() || row.canonical_id}
                            </Link>
                          </li>
                        ))}
                    </ul>
                  </div>
                ) : null}

                {importResult.failed.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Failures</div>
                    <div className="rounded border bg-muted/40 p-3 text-sm space-y-1">
                      {importResult.failed.slice(0, 20).map((f) => (
                        <div key={f.feature_index} className="flex gap-2">
                          <div className="w-16 text-muted-foreground">#{f.feature_index + 1}</div>
                          <div className="flex-1">{f.error}</div>
                        </div>
                      ))}
                      {importResult.failed.length > 20 ? (
                        <div className="text-muted-foreground">
                          (Showing first 20 of {importResult.failed.length} failures.)
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                <div className="flex items-center gap-2">
                  <Link to={backHref}>
                    <Button type="button">Back to canonicals</Button>
                  </Link>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setStep("upload")
                      setGeojsonText("")
                      setUploadedFileName(null)
                      setParsedGeojson(null)
                      setAnalyzeResult(null)
                      setDerivedRows(null)
                      setReviewEdits({})
                      setExcluded(new Set())
                      setImportResult(null)
                      setLocationTypeMode("manual")
                      setManualLocationTypeLabel("")
                      setMappings({
                        labelProperty: null,
                        formattedAddressProperty: null,
                        locationTypeProperty: null,
                        locationTypeValue: null,
                      })
                      setMetaMappingRows([])
                    }}
                  >
                    Import another file
                  </Button>
                </div>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">No import results.</div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

