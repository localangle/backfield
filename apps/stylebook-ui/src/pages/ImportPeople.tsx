import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  analyzeImportCsvPeople,
  importCsvPeople,
  type ImportCsvResponse,
  type PersonCsvFieldMappings,
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
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { AlertCircle, CheckCircle2, Loader2, Trash2 } from "lucide-react"

type ImportStep = "upload" | "mapping" | "review" | "importing" | "complete"

const SELECT_NONE = "__none__"
const MAX_CSV_BYTES = 25 * 1024 * 1024

type PersonPreview = {
  index: number
  label: string
  title: string
  affiliation: string
  person_type: string
  public_figure: boolean
  sort_key: string
}

const MAPPING_FIELDS: { key: keyof PersonCsvFieldMappings; label: string; required?: boolean }[] = [
  { key: "label", label: "Name" },
  { key: "full_name", label: "Full name (alternative to name)" },
  { key: "title", label: "Title" },
  { key: "affiliation", label: "Affiliation" },
  { key: "person_type", label: "Type" },
  { key: "public_figure", label: "Public figure" },
  { key: "sort_key", label: "Sort key" },
]

function parseCsvRows(csvContent: string): Record<string, string>[] {
  const lines = csvContent.split(/\r?\n/).filter((line) => line.trim())
  if (lines.length === 0) return []
  const headers = lines[0]!.split(",").map((h) => h.trim().replace(/^"|"$/g, ""))
  const rows: Record<string, string>[] = []
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i]!.split(",").map((v) => v.trim().replace(/^"|"$/g, ""))
    const row: Record<string, string> = {}
    headers.forEach((header, idx) => {
      row[header] = values[idx] ?? ""
    })
    if (Object.values(row).some((v) => v.trim())) rows.push(row)
  }
  return rows
}

function suggestFieldMappings(columns: string[]): PersonCsvFieldMappings {
  const suggestions: PersonCsvFieldMappings = {}
  for (const col of columns) {
    const lower = col.toLowerCase()
    if (!suggestions.first_name && lower.includes("first") && lower.includes("name")) {
      suggestions.first_name = col
    }
    if (!suggestions.last_name && lower.includes("last") && lower.includes("name")) {
      suggestions.last_name = col
    }
    if (
      !suggestions.full_name &&
      (lower === "name" || lower === "full_name" || lower.includes("full"))
    ) {
      suggestions.full_name = col
    }
    if (!suggestions.label && lower === "label") {
      suggestions.label = col
    }
    if (!suggestions.title && (lower === "title" || lower.includes("job"))) {
      suggestions.title = col
    }
    if (
      !suggestions.affiliation &&
      (lower === "affiliation" || lower.includes("organization") || lower.includes("company"))
    ) {
      suggestions.affiliation = col
    }
    if (!suggestions.public_figure && lower.includes("public")) {
      suggestions.public_figure = col
    }
    if (!suggestions.person_type && (lower === "type" || lower === "person_type")) {
      suggestions.person_type = col
    }
    if (!suggestions.sort_key && lower.includes("sort")) {
      suggestions.sort_key = col
    }
  }
  return suggestions
}

function readMappedValue(
  row: Record<string, string>,
  mappings: PersonCsvFieldMappings,
  field: keyof PersonCsvFieldMappings,
): string {
  const col = mappings[field]
  if (col && row[col] != null) return String(row[col]).trim()
  return (row[field] ?? "").trim()
}

function derivePreviewLabel(
  row: Record<string, string>,
  mappings: PersonCsvFieldMappings,
  index: number,
): string {
  const label = readMappedValue(row, mappings, "label")
  if (label) return label
  const fullName = readMappedValue(row, mappings, "full_name")
  if (fullName) return fullName
  const first = readMappedValue(row, mappings, "first_name")
  const last = readMappedValue(row, mappings, "last_name")
  if (first && last) return `${first} ${last}`.trim()
  if (first) return first
  if (last) return last
  for (const [key, value] of Object.entries(row)) {
    if (value && (key.toLowerCase().includes("name") || key.toLowerCase().includes("person"))) {
      return value.trim()
    }
  }
  return `Person ${index + 1}`
}

function parsePublicFigure(row: Record<string, string>, mappings: PersonCsvFieldMappings): boolean {
  const raw = readMappedValue(row, mappings, "public_figure")
  if (!raw) return false
  return ["true", "1", "yes", "y"].includes(raw.toLowerCase())
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

export default function ImportPeople() {
  const { showError } = useAppMessage()
  const { filterScopeSuffix, stylebookSlug, catalogBasePath } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()

  const [csvText, setCsvText] = useState("")
  const [csvData, setCsvData] = useState<Record<string, string>[]>([])
  const [availableColumns, setAvailableColumns] = useState<string[]>([])
  const [sampleRow, setSampleRow] = useState<Record<string, string> | null>(null)
  const [fieldMappings, setFieldMappings] = useState<PersonCsvFieldMappings>({})
  const [deletedRows, setDeletedRows] = useState<Set<number>>(new Set())
  const [importStep, setImportStep] = useState<ImportStep>("upload")
  const [loading, setLoading] = useState(false)
  const [importResult, setImportResult] = useState<ImportCsvResponse | null>(null)

  const peopleListHref = `${catalogBasePath}/people/canonical${filterScopeSuffix}`

  const personPreviews: PersonPreview[] = useMemo(() => {
    if (!csvData.length) return []
    return csvData
      .map((row, index) => ({
        index,
        label: derivePreviewLabel(row, fieldMappings, index),
        title: readMappedValue(row, fieldMappings, "title"),
        affiliation: readMappedValue(row, fieldMappings, "affiliation"),
        person_type: readMappedValue(row, fieldMappings, "person_type"),
        public_figure: parsePublicFigure(row, fieldMappings),
        sort_key: readMappedValue(row, fieldMappings, "sort_key"),
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
      const analysis = await analyzeImportCsvPeople(stylebookSlug, csvContent)
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
    if (!stylebookSlug || personPreviews.length === 0) return
    const includedRows = csvData.filter((_, index) => !deletedRows.has(index))
    const csvForImport = rowsToCsv(includedRows, availableColumns)
    try {
      setLoading(true)
      setImportStep("importing")
      const result = await importCsvPeople(stylebookSlug, csvForImport, fieldMappings)
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

  function mappingSelect(
    field: keyof PersonCsvFieldMappings,
    placeholder: string,
  ) {
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
              { label: "People", to: peopleListHref },
              { label: "Import" },
            ]}
          />
          <h1 className="text-3xl font-bold">Import people</h1>
        </div>
        <div className="flex gap-2">
          <Link to={`${catalogBasePath}/people/candidates${filterScopeSuffix}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={peopleListHref}>
            <Button variant="outline">People</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Import from CSV</CardTitle>
          <CardDescription>
            {importStep === "upload" && "Upload a CSV file or paste data to begin"}
            {importStep === "mapping" && "Map columns to person fields"}
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
                  placeholder={"name,title,affiliation\nJane Doe,Mayor,City Hall"}
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
                    <div className="mt-1">{mappingSelect(key, `Select column for ${label.toLowerCase()}`)}</div>
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
                  {personPreviews.length} row{personPreviews.length === 1 ? "" : "s"} will be
                  imported.
                  {deletedRows.size > 0
                    ? ` ${deletedRows.size} row${deletedRows.size === 1 ? "" : "s"} excluded.`
                    : null}
                </AlertDescription>
              </Alert>
              <div className="overflow-x-auto rounded-md border max-h-[520px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12">#</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Affiliation</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Public figure</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {personPreviews.map((preview) => (
                      <TableRow key={preview.index}>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {preview.index + 1}
                        </TableCell>
                        <TableCell>{preview.label}</TableCell>
                        <TableCell>{preview.title || "—"}</TableCell>
                        <TableCell>{preview.affiliation || "—"}</TableCell>
                        <TableCell>{preview.person_type || "—"}</TableCell>
                        <TableCell>{preview.public_figure ? "Yes" : "No"}</TableCell>
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
                  disabled={loading || !canEdit || personPreviews.length === 0}
                >
                  Import {personPreviews.length} person{personPreviews.length === 1 ? "" : "s"}
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
                  Created {importResult.created_count} person
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
                        to={`${catalogBasePath}/people/canonical/${row.canonical_id}${filterScopeSuffix}`}
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
                <Link to={peopleListHref}>
                  <Button>View people</Button>
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
