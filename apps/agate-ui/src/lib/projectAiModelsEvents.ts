/** Notifies open flow node panels that project model availability or defaults changed. */

export const PROJECT_AI_MODELS_CHANGED_EVENT = 'agate:project-ai-models-changed'

export type ProjectAiModelsChangedDetail = {
  projectId: number
}

export function dispatchProjectAiModelsChanged(projectId: number): void {
  window.dispatchEvent(
    new CustomEvent<ProjectAiModelsChangedDetail>(PROJECT_AI_MODELS_CHANGED_EVENT, {
      detail: { projectId },
    }),
  )
}
