export type NodePanelTabId = 'settings' | 'info' | 'models' | 'prompts' | 'outputs'

export const NODE_PANEL_TAB_LABELS: Record<NodePanelTabId, string> = {
  settings: 'Settings',
  info: 'Info',
  models: 'Models',
  prompts: 'Prompts',
  outputs: 'Outputs',
}

/** Which configuration tabs apply to each node type in the guided flow builder. */
export function getNodePanelTabs(
  nodeType: string,
  options?: { hasRunOutput?: boolean },
): NodePanelTabId[] {
  const hasRunOutput = options?.hasRunOutput === true

  switch (nodeType) {
    case 'TextInput':
    case 'S3Input':
      return hasRunOutput ? ['settings', 'outputs'] : ['settings']
    case 'JSONInput':
      return hasRunOutput ? ['settings', 'info', 'outputs'] : ['settings', 'info']
    case 'PlaceExtract':
      return hasRunOutput
        ? ['settings', 'info', 'models', 'prompts', 'outputs']
        : ['settings', 'info', 'models', 'prompts']
    case 'GeocodeAgent':
      return hasRunOutput ? ['settings', 'models', 'outputs'] : ['settings', 'models']
    case 'Output':
      return hasRunOutput ? ['outputs'] : []
    case 'DBOutput':
      return ['settings']
    default:
      return ['settings']
  }
}
