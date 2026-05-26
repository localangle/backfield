import { createContext, useContext, type ReactNode } from 'react'

import type { NodePanelTabId } from '@/lib/nodePanelTabs'

const NodePanelTabContext = createContext<NodePanelTabId>('settings')

type NodePanelTabProviderProps = {
  activeTab: NodePanelTabId
  children: ReactNode
}

export function NodePanelTabProvider({ activeTab, children }: NodePanelTabProviderProps) {
  return <NodePanelTabContext.Provider value={activeTab}>{children}</NodePanelTabContext.Provider>
}

export function useNodePanelTab(): NodePanelTabId {
  return useContext(NodePanelTabContext)
}

type NodePanelTabGateProps = {
  tab: NodePanelTabId
  children: ReactNode
}

/** Renders children only when the active panel tab matches. */
export function NodePanelTabGate({ tab, children }: NodePanelTabGateProps) {
  const activeTab = useNodePanelTab()
  if (activeTab !== tab) return null
  return <>{children}</>
}
