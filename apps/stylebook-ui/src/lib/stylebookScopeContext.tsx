import { createContext, useContext, type ReactNode } from "react"

type StylebookScopeContextValue = {
  selectedStylebookLabel: string
  /** True after Layout has finished loading the project list used for default ``project_scope``. */
  workflowProjectsReady: boolean
  /** False when the signed-in user has no projects Layout can scope to. */
  hasWorkflowProjects: boolean
}

const StylebookScopeContext = createContext<StylebookScopeContextValue>({
  selectedStylebookLabel: "Stylebook",
  workflowProjectsReady: false,
  hasWorkflowProjects: false,
})

export function StylebookScopeProvider({
  selectedStylebookLabel,
  workflowProjectsReady,
  hasWorkflowProjects,
  children,
}: {
  selectedStylebookLabel: string
  workflowProjectsReady: boolean
  hasWorkflowProjects: boolean
  children: ReactNode
}) {
  return (
    <StylebookScopeContext.Provider
      value={{ selectedStylebookLabel, workflowProjectsReady, hasWorkflowProjects }}
    >
      {children}
    </StylebookScopeContext.Provider>
  )
}

export function useSelectedStylebookLabel(): string {
  return useContext(StylebookScopeContext).selectedStylebookLabel
}

export function useWorkflowProjectScopeReady(): {
  workflowProjectsReady: boolean
  hasWorkflowProjects: boolean
} {
  const { workflowProjectsReady, hasWorkflowProjects } = useContext(StylebookScopeContext)
  return { workflowProjectsReady, hasWorkflowProjects }
}
