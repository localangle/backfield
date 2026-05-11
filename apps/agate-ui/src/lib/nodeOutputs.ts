/**
 * Re-export canonical node-output key helpers from `@backfield/ui`
 * (single source; matches `execute_graph` in `backfield_agate.executor`).
 */
export {
  NODE_OUTPUT_KEY_INDEX,
  buildNodeIdToPublicOutputKey,
  getNodeOutputById,
  getNodeOutputKeyMap,
  nodeOutputLookupFromGraphSpec,
  nodeOutputLookupFromReactFlow,
  type NodeOutputLookupSpec,
} from '@backfield/ui/nodeOutputs'
