import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type WizardStep = "upload" | "mapping" | "review" | "importing" | "complete"

const STEP_LABELS: Record<WizardStep, string> = {
  upload: "Upload",
  mapping: "Mapping",
  review: "Review",
  importing: "Importing",
  complete: "Complete",
}

export default function ImportLocations() {
  const [searchParams] = useSearchParams()
  const projectSlug = useMemo(() => searchParams.get("project") || "", [searchParams])
  const [step, setStep] = useState<WizardStep>("upload")

  useEffect(() => {
    setStep("upload")
  }, [projectSlug])

  const backHref = useMemo(() => {
    const q = projectSlug ? `?project=${encodeURIComponent(projectSlug)}` : ""
    return `/locations/canonical${q}`
  }, [projectSlug])

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
            Upload → Mapping → Review → Importing → Complete (shell; functionality will be added in subsequent issues).
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
    </div>
  )
}

