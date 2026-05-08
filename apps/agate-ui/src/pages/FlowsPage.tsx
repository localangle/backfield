import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  listProjects,
  listGraphs,
  deleteGraph,
  updateGraph,
  createGraph,
  type Project,
  type Graph,
  type GraphCreate,
} from '@/lib/api'
import { formatDateCentral } from '@/lib/utils'
import { Loader2, Copy, Trash2 } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export default function FlowsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [graphs, setGraphs] = useState<Graph[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [flowToDelete, setFlowToDelete] = useState<Graph | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      setLoading(true)
      const [projectsData, graphsData] = await Promise.all([listProjects(), listGraphs()])
      setProjects(projectsData)
      setGraphs(graphsData)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteFlow = (flow: Graph) => {
    setFlowToDelete(flow)
    setDeleteDialogOpen(true)
  }

  const handleDuplicateFlow = async (flow: Graph) => {
    try {
      const duplicateData: GraphCreate = {
        name: `Copy of ${flow.name}`,
        project_id: flow.project_id,
        spec: flow.spec,
      }
      const newGraph = await createGraph(duplicateData)
      setGraphs((prev) => [...prev, newGraph])
      navigate(`/flow/${newGraph.id}`)
    } catch (error) {
      console.error('Failed to duplicate flow:', error)
    }
  }

  const confirmDeleteFlow = async () => {
    if (!flowToDelete) return
    try {
      await deleteGraph(flowToDelete.id)
      setGraphs((prev) => prev.filter((g) => g.id !== flowToDelete.id))
      setDeleteDialogOpen(false)
      setFlowToDelete(null)
    } catch (error) {
      console.error('Failed to delete flow:', error)
    }
  }

  const handleProjectChange = async (graph: Graph, newProjectId: number) => {
    try {
      const updateData: GraphCreate = {
        name: graph.name,
        project_id: newProjectId,
        spec: graph.spec,
      }
      const updated = await updateGraph(graph.id, updateData)
      setGraphs((prev) => prev.map((g) => (g.id === graph.id ? updated : g)))
    } catch (error) {
      console.error('Failed to update flow project:', error)
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
    <>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Flows</h1>
            <p className="text-muted-foreground mt-1">View all flows across all projects</p>
          </div>
        </div>

        {graphs.length === 0 ? (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-muted-foreground mb-4">
                  No flows found. Create a project and add flows to get started.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="text-left p-4 font-medium">Name</th>
                    <th className="text-left p-4 font-medium">Project</th>
                    <th className="text-left p-4 font-medium">Nodes</th>
                    <th className="text-left p-4 font-medium">Created</th>
                    <th className="text-right p-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {graphs.map((graph) => (
                    <tr
                      key={graph.id}
                      className="border-b last:border-b-0 hover:bg-muted/[0.07] transition-colors"
                    >
                      <td
                        className="p-4 cursor-pointer"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        <div className="font-medium">{graph.name}</div>
                      </td>
                      <td className="p-4" onClick={(e) => e.stopPropagation()}>
                        <Select
                          value={graph.project_id.toString()}
                          onValueChange={(value) =>
                            handleProjectChange(graph, parseInt(value, 10))
                          }
                        >
                          <SelectTrigger className="w-[180px]">
                            <SelectValue placeholder="Select project" />
                          </SelectTrigger>
                          <SelectContent>
                            {projects.map((project) => (
                              <SelectItem key={project.id} value={project.id.toString()}>
                                {project.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td
                        className="p-4 cursor-pointer"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        <div className="flex flex-wrap gap-1">
                          {graph.spec.nodes.map((node) => (
                            <span
                              key={node.id}
                              className="text-xs px-2 py-1 bg-secondary rounded-md"
                            >
                              {node.type}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td
                        className="p-4 text-sm text-muted-foreground cursor-pointer"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        {formatDateCentral(graph.created_at, { includeTime: false })}
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDuplicateFlow(graph)
                            }}
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                            title="Duplicate flow"
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDeleteFlow(graph)
                            }}
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                            title="Delete flow"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Flow</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{flowToDelete?.name}&quot;? This action cannot
              be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteFlow}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
