export type NodePanelTabId =
  | 'settings'
  | 'stylebook'
  | 'connections'
  | 'info'
  | 'models'
  | 'prompts'
  | 'outputs'

export const NODE_PANEL_TAB_LABELS: Record<NodePanelTabId, string> = {
  settings: 'Settings',
  stylebook: 'Stylebook',
  connections: 'Connections',
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
    case 'CustomExtract':
      return ['settings', 'prompts', 'outputs', 'info']
    case 'GeocodeAgent':
      return ['settings', 'models']
    case 'EmbedText':
      return ['settings', 'info']
    case 'EmbedImages':
      return ['settings', 'info']
    case 'Gather':
      return hasRunOutput ? ['settings', 'info', 'outputs'] : ['settings', 'info']
    case 'DocumentChunker':
      return hasRunOutput ? ['settings', 'info', 'outputs'] : ['settings', 'info']
    case 'ArticleMetadata':
      return ['settings', 'prompts', 'outputs', 'info']
    case 'Output':
      return hasRunOutput ? ['outputs'] : []
    case 'DBOutput':
      return ['settings', 'stylebook', 'connections']
    case 'S3Output':
      return hasRunOutput ? ['settings', 'outputs'] : ['settings']
    default:
      return ['settings']
  }
}
