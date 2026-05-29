import { useEffect, useState } from 'react'

import type { PageBreadcrumbItem } from '@/components/PageBreadcrumbs'
import { getProject, type Project } from '@/lib/api'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'

/** Workspaces → workspace → project prefix used across flow and run screens. */
export function buildProjectBreadcrumbItems(options: {
  project: Project | null
  workspace: WorkspaceWithProjects | null
  tail?: PageBreadcrumbItem[]
}): PageBreadcrumbItem[] {
  const items: PageBreadcrumbItem[] = [{ label: 'Workspaces', to: '/' }]
  if (options.workspace) {
    items.push({
      label: options.workspace.name,
      to: `/workspace/${encodeURIComponent(options.workspace.slug)}`,
    })
  }
  if (options.project) {
    items.push({
      label: options.project.name,
      to: `/project/${encodeURIComponent(options.project.slug)}`,
    })
  }
  if (options.tail?.length) {
    items.push(...options.tail)
  }
  return items
}

/** Resolve project and parent workspace for breadcrumb navigation. */
export function useProjectAndWorkspace(projectId: number | null | undefined): {
  project: Project | null
  workspace: WorkspaceWithProjects | null
} {
  const [project, setProject] = useState<Project | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceWithProjects | null>(null)

  useEffect(() => {
    if (projectId == null) {
      setProject(null)
      return
    }
    let cancelled = false
    void getProject(projectId)
      .then((row) => {
        if (!cancelled) setProject(row)
      })
      .catch(() => {
        if (!cancelled) setProject(null)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    if (project?.workspace_id == null) {
      setWorkspace(null)
      return
    }
    let cancelled = false
    void listMyWorkspaces()
      .then((rows) => {
        if (!cancelled) {
          setWorkspace(rows.find((row) => row.id === project.workspace_id) ?? null)
        }
      })
      .catch(() => {
        if (!cancelled) setWorkspace(null)
      })
    return () => {
      cancelled = true
    }
  }, [project?.workspace_id])

  return { project, workspace }
}
