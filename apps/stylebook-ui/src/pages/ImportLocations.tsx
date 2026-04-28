import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
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
  type ImportGeoJsonResponse,
} from "@/lib/api"
import {
  buildFeatureCollectionForImport,
  canProceedFromMapping,
  deriveImportRows,
  normalizeFeatureCollectionForImport,
  validateDerivedRows,
  type DerivedImportRow,
  type GeoJsonFeatureCollection,
  type GeoJsonFieldMappings,
  type ReviewEditsByFeatureIndex,
} from "@/lib/import/geojsonImport"

type WizardStep = "upload" | "mapping" | "review" | "importing" | "complete"

const MAX_GEOJSON_BYTES = 25 * 1024 * 1024

const STEP_LABELS: Record<WizardStep, string> = {
  upload: "Upload",
  mapping: "Mapping",
  review: "Review",
  importing: "Importing",
  complete: "Complete",
}

export default function ImportLocations() {
  const [searchParams] = useSearchParams()
  const { showError } = useAppMessage()
  const projectSlug = useMemo(() => searchParams.get("project") || "", [searchParams])
  const [step, setStep] = useState<WizardStep>("upload")
  const [geojsonText, setGeojsonText] = useState<string>("")
  const [geojsonTooLarge, setGeojsonTooLarge] = useState(false)
  const [parsedGeojson, setParsedGeojson] = useState<Record<string, unknown> | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeGeoJsonResponse | null>(null)
  const [mappings, setMappings] = useState<GeoJsonFieldMappings>({
    labelProperty: null,
    locationTypeProperty: null,
    formattedAddressProperty: null,
    locationTypeValue: null,
  })
  const [derivedRows, setDerivedRows] = useState<DerivedImportRow[] | null>(null)
  const [reviewEdits, setReviewEdits] = useState<ReviewEditsByFeatureIndex>({})
  const [excluded, setExcluded] = useState<Set<number>>(() => new Set())
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportGeoJsonResponse | null>(null)

  useEffect(() => {
    setStep("upload")
    setGeojsonText("")
    setGeojsonTooLarge(false)
    setParsedGeojson(null)
    setAnalyzeResult(null)
    setMappings({
      labelProperty: null,
      locationTypeProperty: null,
      formattedAddressProperty: null,
      locationTypeValue: null,
    })
    setDerivedRows(null)
    setReviewEdits({})
    setExcluded(new Set())
    setImporting(false)
    setImportResult(null)
  }, [projectSlug])

  const backHref = useMemo(() => {
    const q = projectSlug ? `?project=${encodeURIComponent(projectSlug)}` : ""
    return `/locations/canonical${q}`
  }, [projectSlug])

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

  const canAnalyze = Boolean(projectSlug && parsedGeojson && step === "upload" && !analyzing)
  const availableProperties = analyzeResult?.available_properties ?? []

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

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Import locations (GeoJSON)</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {projectSlug ? (
              <>
                Project: <span className="font-medium">{projectSlug}</span>
              </>
            ) : (
              "Project: —"
            )}
          </p>
        </div>
        <Link to={backHref}>
          <Button variant="outline">Back to canonicals</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Wizard</CardTitle>
          <CardDescription>
            Upload → Mapping → Review → Importing → Complete
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {(Object.keys(STEP_LABELS) as WizardStep[]).map((s) => (
              <Button
                key={s}
                type="button"
                variant={s === step ? "default" : "outline"}
                onClick={() => setStep(s)}
              >
                {STEP_LABELS[s]}
              </Button>
            ))}
          </div>
          <div className="text-sm text-muted-foreground">
            Current step: <span className="font-medium text-foreground">{STEP_LABELS[step]}</span>
          </div>
        </CardContent>
      </Card>

      {step === "upload" ? (
        <Card>
          <CardHeader>
            <CardTitle>Upload or paste GeoJSON</CardTitle>
            <CardDescription>
              Choose a GeoJSON file or paste a FeatureCollection, then click Analyze to discover available properties.
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
                    setParsedGeojson(null)
                    setAnalyzeResult(null)
                    setGeojsonTooLarge(true)
                    showError("GeoJSON file exceeds 25MB. Please split it into smaller files.")
                    return
                  }
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

            <div className="space-y-2">
              <Label>Or paste GeoJSON</Label>
              <Textarea
                value={geojsonText}
                onChange={(e) => {
                  const t = e.target.value
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

            <div className="flex items-center gap-2">
              <Button
                type="button"
                disabled={!canAnalyze}
                onClick={async () => {
                  if (!projectSlug || !parsedGeojson) return
                  setAnalyzing(true)
                  try {
                    const res = await analyzeImportGeoJson(projectSlug, parsedGeojson)
                    setAnalyzeResult(res)
                  } catch (e) {
                    console.error(e)
                    showError(e instanceof Error ? e.message : "Analyze failed")
                  } finally {
                    setAnalyzing(false)
                  }
                }}
              >
                {analyzing ? "Analyzing…" : "Analyze"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setGeojsonText("")
                  setParsedGeojson(null)
                  setAnalyzeResult(null)
                }}
              >
                Clear
              </Button>
            </div>

            {analyzeResult ? (
              <div className="space-y-2 pt-2">
                <div className="text-sm">
                  Features: <span className="font-medium">{analyzeResult.feature_count}</span>
                </div>
                <div className="text-sm">
                  Available properties ({analyzeResult.available_properties.length}):
                </div>
                <div className="flex flex-wrap gap-2">
                  {analyzeResult.available_properties.map((p) => (
                    <span
                      key={p}
                      className="rounded border bg-muted px-2 py-1 text-xs text-muted-foreground"
                    >
                      {p}
                    </span>
                  ))}
                </div>
                <div className="pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!parsedGeojson || !projectSlug}
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
              Choose which GeoJSON properties map to required canonical fields. Import requires label, type, and geometry.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label>Label / name property</Label>
                <Select
                  value={mappings.labelProperty ?? ""}
                  onValueChange={(v) =>
                    setMappings((prev) => ({ ...prev, labelProperty: v ? v : null }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select property…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None</SelectItem>
                    {availableProperties.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Location type property</Label>
                <Select
                  value={mappings.locationTypeProperty ?? ""}
                  onValueChange={(v) =>
                    setMappings((prev) => ({ ...prev, locationTypeProperty: v ? v : null }))
                  }
                  disabled={Boolean((mappings.locationTypeValue ?? "").trim())}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select property…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None</SelectItem>
                    {availableProperties.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Disabled when “Type for all” is set.
                </p>
              </div>

              <div className="space-y-2">
                <Label>Formatted address property (optional)</Label>
                <Select
                  value={mappings.formattedAddressProperty ?? ""}
                  onValueChange={(v) =>
                    setMappings((prev) => ({ ...prev, formattedAddressProperty: v ? v : null }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select property…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None</SelectItem>
                    {availableProperties.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Type for all imported locations (optional override)</Label>
              <Input
                value={mappings.locationTypeValue ?? ""}
                placeholder="e.g. city"
                onChange={(e) => {
                  const v = e.target.value
                  setMappings((prev) => ({ ...prev, locationTypeValue: v }))
                }}
              />
              <p className="text-xs text-muted-foreground">
                When set, this value overrides the per-feature type mapping.
              </p>
            </div>

            {validationSummary ? (
              <div className="rounded border bg-muted/40 p-3 text-sm">
                <div>
                  Rows: <span className="font-medium">{validationSummary.total_rows}</span>
                </div>
                <div className="mt-1 text-muted-foreground">
                  Missing label: {validationSummary.missing_label_count} • Missing type:{" "}
                  {validationSummary.missing_location_type_count} • Missing geometry:{" "}
                  {validationSummary.missing_geometry_count}
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Analyze a FeatureCollection first.
              </div>
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
                  setStep("review")
                }}
              >
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

                <div className="space-y-2">
                  <div className="text-sm font-medium">Computed import payload (debug)</div>
                  <Textarea
                    readOnly
                    value={importPayload ? JSON.stringify(importPayload, null, 2) : ""}
                    className="min-h-[12rem] font-mono text-xs"
                  />
                </div>
              </>
            )}
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={() => setStep("mapping")}>
                Back to mapping
              </Button>
              <Button
                type="button"
                disabled={!projectSlug || !importPayload || importPayload.features.length === 0 || importing}
                onClick={async () => {
                  if (!projectSlug || !importPayload) return
                  setImporting(true)
                  setStep("importing")
                  try {
                    const res = await importGeoJson(projectSlug, importPayload, {
                      label_property: mappings.labelProperty ?? null,
                      location_type_property: mappings.locationTypeProperty ?? null,
                      formatted_address_property: mappings.formattedAddressProperty ?? null,
                      location_type_value: mappings.locationTypeValue ?? null,
                    })
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
                      setParsedGeojson(null)
                      setAnalyzeResult(null)
                      setDerivedRows(null)
                      setReviewEdits({})
                      setExcluded(new Set())
                      setImportResult(null)
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

