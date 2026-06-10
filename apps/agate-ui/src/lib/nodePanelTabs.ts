export type NodePanelTabId = 'settings' | 'stylebook' | 'info' | 'models' | 'prompts' | 'outputs'

export const NODE_PANEL_TAB_LABELS: Record<NodePanelTabId, string> = {
  settings: 'Settings',
  stylebook: 'Stylebook',
  info: 'Info',
  models: 'Models',
  prompts: 'Prompt',
  outputs: 'Output',
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
    case 'PersonExtract':
    case 'OrganizationExtract':
      return ['settings', 'prompts', 'outputs', 'info']
    case 'GeocodeAgent':
      return ['settings', 'models']
    case 'EmbedText':
      return ['settings', 'info']
    case 'Output':
      return hasRunOutput ? ['outputs'] : []
    case 'DBOutput':
      return ['settings', 'stylebook']
    default:
      return ['settings']
  }
}
