import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  analyzeImportCsvOrganizations,
  importCsvOrganizations,
  type ImportCsvResponse,
  type OrganizationCsvFieldMappings,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { parseCsvRows } from "@/lib/parseCsv"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { AlertCircle, CheckCircle2, Loader2, Trash2 } from "lucide-react"

type ImportStep = "upload" | "mapping" | "review" | "importing" | "complete"

const SELECT_NONE = "__none__"
const MAX_CSV_BYTES = 25 * 1024 * 1024

type OrganizationPreview = {
  index: number
  label: string
  organization_type: string
}

const MAPPING_FIELDS: {
  key: keyof OrganizationCsvFieldMappings
  label: string
  required?: boolean
}[] = [
  { key: "label", label: "Name", required: true },
  { key: "organization_type", label: "Type" },
]

const CSV_PASTE_PLACEHOLDER = [
  "name,type",
  "Chicago Public Schools,school_district",
  "City of Chicago,government",
].join("\n")

function suggestFieldMappings(columns: string[]): OrganizationCsvFieldMappings {
  const suggestions: OrganizationCsvFieldMappings = {}
  for (const col of columns) {
    const lower = col.toLowerCase()
    if (
      !suggestions.label &&
      (lower === "name" || lower === "label" || lower === "full_name" || lower === "organization")
    ) {
      suggestions.label = col
    }
    if (
      !suggestions.organization_type &&
      (lower === "type" || lower === "organization_type" || lower === "org_type")
    ) {
      suggestions.organization_type = col
    }
  }
  return suggestions
}

function readMappedValue(
  row: Record<string, string>,
  mappings: OrganizationCsvFieldMappings,
  field: keyof OrganizationCsvFieldMappings,
): string {
  const col = mappings[field]
  if (col && row[col] != null) return String(row[col]).trim()
  return (row[field] ?? "").trim()
}

function derivePreviewLabel(
  row: Record<string, string>,
  mappings: OrganizationCsvFieldMappings,
  index: number,
): string {
  const label = readMappedValue(row, mappings, "label")
  if (label) return label
  for (const [key, value] of Object.entries(row)) {
    if (
      value &&
      (key.toLowerCase().includes("name") || key.toLowerCase().includes("organization"))
    ) {
      return value.trim()
    }
  }
  return `Organization ${index + 1}`
}

function rowsToCsv(rows: Record<string, string>[], columns: string[]): string {
  const escape = (v: string) => {
    if (/[",\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`
    return v
  }
  const header = columns.map(escape).join(",")
  const body = rows.map((row) => columns.map((col) => escape(row[col] ?? "")).join(","))
  return [header, ...body].join("\n")
}

export default function ImportOrganizations() {
  const { showError } = useAppMessage()
  const { filterScopeSuffix, stylebookSlug, catalogBasePath } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()

  const [csvText, setCsvText] = useState("")
  const [csvData, setCsvData] = useState<Record<string, string>[]>([])
  const [availableColumns, setAvailableColumns] = useState<string[]>([])
  const [sampleRow, setSampleRow] = useState<Record<string, string> | null>(null)
  const [fieldMappings, setFieldMappings] = useState<OrganizationCsvFieldMappings>({})
  const [deletedRows, setDeletedRows] = useState<Set<number>>(new Set())
  const [importStep, setImportStep] = useState<ImportStep>("upload")
  const [loading, setLoading] = useState(false)
  const [importResult, setImportResult] = useState<ImportCsvResponse | null>(null)

  const organizationsListHref = `${catalogBasePath}/organizations/canonical${filterScopeSuffix}`

  const organizationPreviews: OrganizationPreview[] = useMemo(() => {
    if (!csvData.length) return []
    return csvData
      .map((row, index) => ({
        index,
        label: derivePreviewLabel(row, fieldMappings, index),
        organization_type: readMappedValue(row, fieldMappings, "organization_type"),
      }))
      .filter((row) => !deletedRows.has(row.index))
  }, [csvData, fieldMappings, deletedRows])

  async function processCsv(csvContent: string) {
    if (new Blob([csvContent]).size > MAX_CSV_BYTES) {
      showError("File exceeds 25MB limit.")
      return false
    }
    try {
      if (!stylebookSlug) return false
      const analysis = await analyzeImportCsvOrganizations(stylebookSlug, csvContent)
      setCsvData(parseCsvRows(csvContent))
      setAvailableColumns(analysis.available_columns)
      setSampleRow(analysis.sample_row)
      setFieldMappings(suggestFieldMappings(analysis.available_columns))
      setDeletedRows(new Set())
      setImportStep("mapping")
      return true
    } catch (error) {
      console.error("Failed to analyze CSV:", error)
      showError("Could not read this file. Check that it is a valid CSV with a header row.")
      return false
    }
  }

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showError("Please upload a .csv file.")
      return
    }
    try {
      setLoading(true)
      const text = await file.text()
      setCsvText(text)
      await processCsv(text)
    } finally {
      setLoading(false)
      event.target.value = ""
    }
  }

  async function handleAnalyze() {
    if (!csvText.trim()) {
      showError("Paste CSV data or upload a file first.")
      return
    }
    try {
      setLoading(true)
      await processCsv(csvText)
    } finally {
      setLoading(false)
    }
  }

  function handleReset() {
    setCsvText("")
    setCsvData([])
    setAvailableColumns([])
    setSampleRow(null)
    setFieldMappings({})
    setDeletedRows(new Set())
    setImportResult(null)
    setImportStep("upload")
  }

  function handleDeleteRow(index: number) {
    setDeletedRows((prev) => new Set(prev).add(index))
  }

  async function handleImport() {
    if (!stylebookSlug || organizationPreviews.length === 0) return
    const includedRows = csvData.filter((_, index) => !deletedRows.has(index))
    const csvForImport = rowsToCsv(includedRows, availableColumns)
    try {
      setLoading(true)
      setImportStep("importing")
      const result = await importCsvOrganizations(stylebookSlug, csvForImport, fieldMappings)
      setImportResult(result)
      setImportStep("complete")
    } catch (error) {
      console.error("Failed to import CSV:", error)
      showError(error instanceof Error ? error.message : "Import failed")
      setImportStep("review")
    } finally {
      setLoading(false)
    }
  }

  function mappingSelect(field: keyof OrganizationCsvFieldMappings, placeholder: string) {
    const value = fieldMappings[field] || SELECT_NONE
    return (
      <Select
        value={value}
        onValueChange={(v) =>
          setFieldMappings((prev) => ({
            ...prev,
            [field]: v === SELECT_NONE ? "" : v,
          }))
        }
      >
        <SelectTrigger>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SELECT_NONE}>None</SelectItem>
          {availableColumns.map((col) => (
            <SelectItem key={col} value={col}>
              {col}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "Organizations", to: organizationsListHref },
              { label: "Import" },
            ]}
          />
          <h1 className="text-3xl font-bold">Import organizations</h1>
        </div>
        <div className="flex gap-2">
          <Link to={`${catalogBasePath}/organizations/candidates${filterScopeSuffix}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={organizationsListHref}>
            <Button variant="outline">Organizations</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Import from CSV</CardTitle>
          <CardDescription>
            {importStep === "upload" && "Upload a CSV file or paste data to begin"}
            {importStep === "mapping" && "Map columns to organization fields"}
            {importStep === "review" && "Review rows before importing"}
            {importStep === "importing" && "Importing…"}
            {importStep === "complete" && "Import complete"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {importStep === "upload" && (
            <>
              <div>
                <Label>Upload CSV file</Label>
                <Input
                  type="file"
                  accept=".csv"
                  className="mt-2 cursor-pointer"
                  onChange={(e) => void handleFileUpload(e)}
                  disabled={loading || !canEdit}
                />
              </div>
              <div className="relative py-2">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">Or</span>
                </div>
              </div>
              <div>
                <Label>Paste CSV</Label>
                <Textarea
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  placeholder={CSV_PASTE_PLACEHOLDER}
                  className="mt-2 min-h-[240px] font-mono text-sm"
                  disabled={!canEdit}
                />
              </div>
              <Button
                onClick={() => void handleAnalyze()}
                disabled={loading || !canEdit || !csvText.trim() || !stylebookSlug}
              >
                {loading ? "Analyzing…" : "Continue"}
              </Button>
            </>
          )}

          {importStep === "mapping" && (
            <>
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  Found {csvData.length} row{csvData.length === 1 ? "" : "s"} with{" "}
                  {availableColumns.length} column{availableColumns.length === 1 ? "" : "s"}.
                </AlertDescription>
              </Alert>
              {sampleRow ? (
                <div className="rounded-md bg-muted p-4">
                  <Label className="mb-2 block text-sm font-semibold">Sample row</Label>
                  <pre className="max-h-40 overflow-auto text-xs">
                    {JSON.stringify(sampleRow, null, 2)}
                  </pre>
                </div>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                {MAPPING_FIELDS.map(({ key, label }) => (
                  <div key={key}>
                    <Label>{label}</Label>
                    <div className="mt-1">
                      {mappingSelect(key, `Select column for ${label.toLowerCase()}`)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button onClick={() => setImportStep("review")}>Continue to review</Button>
                <Button variant="outline" onClick={handleReset}>
                  Start over
                </Button>
              </div>
            </>
          )}

          {importStep === "review" && (
            <>
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {organizationPreviews.length} row{organizationPreviews.length === 1 ? "" : "s"}{" "}
                  will be imported.
                  {deletedRows.size > 0
                    ? ` ${deletedRows.size} row${deletedRows.size === 1 ? "" : "s"} excluded.`
                    : null}
                </AlertDescription>
              </Alert>
              <div className="overflow-x-auto rounded-md border max-h-[520px]">
                <Table className="table-fixed w-full min-w-[32rem]">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12">#</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {organizationPreviews.map((preview) => (
                      <TableRow key={preview.index}>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {preview.index + 1}
                        </TableCell>
                        <TableCell className="min-w-0 truncate">{preview.label}</TableCell>
                        <TableCell className="min-w-0 truncate">{preview.organization_type || "—"}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            onClick={() => handleDeleteRow(preview.index)}
                            aria-label="Remove row"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={() => void handleImport()}
                  disabled={loading || !canEdit || organizationPreviews.length === 0}
                >
                  Import {organizationPreviews.length} organization
                  {organizationPreviews.length === 1 ? "" : "s"}
                </Button>
                <Button variant="outline" onClick={() => setImportStep("mapping")}>
                  Back to mapping
                </Button>
                <Button variant="outline" onClick={handleReset}>
                  Start over
                </Button>
              </div>
            </>
          )}

          {importStep === "importing" && (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {importStep === "complete" && importResult && (
            <>
              <Alert variant={importResult.failed_count === 0 ? "default" : "destructive"}>
                {importResult.failed_count === 0 ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                <AlertDescription>
                  Created {importResult.created_count} organization
                  {importResult.created_count === 1 ? "" : "s"}.
                  {importResult.failed_count > 0
                    ? ` ${importResult.failed_count} row${importResult.failed_count === 1 ? "" : "s"} failed.`
                    : null}
                </AlertDescription>
              </Alert>
              {importResult.created.length > 0 ? (
                <ul className="space-y-1 text-sm">
                  {importResult.created.map((row) => (
                    <li key={row.canonical_id}>
                      <Link
                        className="text-primary underline-offset-4 hover:underline"
                        to={`${catalogBasePath}/organizations/canonical/${row.canonical_id}${filterScopeSuffix}`}
                      >
                        {row.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : null}
              {importResult.failed.length > 0 ? (
                <div className="rounded-md bg-muted p-3 text-sm">
                  {importResult.failed.map((row) => (
                    <div key={row.row_index}>
                      Row {row.row_index + 1}: {row.error}
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="flex gap-2">
                <Link to={organizationsListHref}>
                  <Button>View organizations</Button>
                </Link>
                <Button variant="outline" onClick={handleReset}>
                  Import another file
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
