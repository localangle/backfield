import type { FlowGraphModel } from '@/lib/flowGraphModel'
import type { FlowBuilderStep } from '@/lib/flowBuilderSteps'
import type { Node } from 'reactflow'

export type GuidedFlowSnapshot = {
  graphName: string
  graphDescription: string
  publicRunEnabled: boolean
  activeStep: FlowBuilderStep
  completedSteps: FlowBuilderStep[]
  inputNode: Node | null
  outputNode: Node | null
  scaffoldModel: FlowGraphModel | null
  selectedNodeId: string | null
  configureGateActive: boolean
}

export function captureGuidedFlowSnapshot(state: GuidedFlowSnapshot): GuidedFlowSnapshot {
  return {
    graphName: state.graphName,
    graphDescription: state.graphDescription,
    publicRunEnabled: state.publicRunEnabled,
    activeStep: state.activeStep,
    completedSteps: [...state.completedSteps],
    inputNode: state.inputNode ? { ...state.inputNode, data: { ...state.inputNode.data } } : null,
    outputNode: state.outputNode ? { ...state.outputNode, data: { ...state.outputNode.data } } : null,
    scaffoldModel: state.scaffoldModel
      ? {
          ...state.scaffoldModel,
          inputNode: { ...state.scaffoldModel.inputNode, data: { ...state.scaffoldModel.inputNode.data } },
          outputNode: { ...state.scaffoldModel.outputNode, data: { ...state.scaffoldModel.outputNode.data } },
          middleNodes: state.scaffoldModel.middleNodes.map((node) => ({
            ...node,
            data: { ...node.data },
          })),
          branchChildren: { ...state.scaffoldModel.branchChildren },
          serialLinks: { ...state.scaffoldModel.serialLinks },
        }
      : null,
    selectedNodeId: state.selectedNodeId,
    configureGateActive: state.configureGateActive,
  }
}
