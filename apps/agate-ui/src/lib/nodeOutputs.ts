/**
 * Re-export canonical node-output key helpers from `@backfield/ui`
 * (single source; matches `execute_graph` in `agate_runtime.executor`).
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
