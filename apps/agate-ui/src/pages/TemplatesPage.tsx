import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  listTemplates,
  instantiateTemplate,
  listProjects,
  type AgateTemplate,
  type Project,
} from '@/lib/api'
import { Loader2, LayoutTemplate } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<AgateTemplate[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<AgateTemplate | null>(null)
  const [projectId, setProjectId] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const [t, p] = await Promise.all([listTemplates(), listProjects()])
        setTemplates(t)
        setProjects(p)
        if (p.length && !projectId) setProjectId(String(p[0].id))
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const openPicker = (t: AgateTemplate) => {
    setSelectedTemplate(t)
    if (projects.length && !projectId) setProjectId(String(projects[0].id))
    setPickerOpen(true)
  }

  const navigate = useNavigate()

  const handleInstantiate = async () => {
    if (!selectedTemplate || !projectId) return
    try {
      setSubmitting(true)
      const graph = await instantiateTemplate(selectedTemplate.id, {
        project_id: parseInt(projectId, 10),
      })
      setPickerOpen(false)
      navigate(`/flow/${graph.id}/edit`)
    } catch (e) {
      console.error(e)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Templates</h1>
        <p className="text-muted-foreground mt-1">
          Start from a curated flow; a new graph is created in your project.
        </p>
      </div>

      {templates.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No templates available yet.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {templates.map((t) => (
            <Card key={t.id}>
              <CardHeader>
                <LayoutTemplate className="h-8 w-8 text-muted-foreground mb-2" />
                <CardTitle>{t.name}</CardTitle>
                {t.description ? (
                  <CardDescription>{t.description}</CardDescription>
                ) : null}
              </CardHeader>
              <CardContent>
                <Button onClick={() => openPicker(t)} disabled={projects.length === 0}>
                  Use in project
                </Button>
                {projects.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Create a project first to use a template.
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Use template: {selectedTemplate?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label>Project</Label>
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger>
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPickerOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleInstantiate} disabled={!projectId || submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create flow'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
