/**
 * Stylebook UI API surface — re-exports split clients (stylebook-api + Agate projects).
 */

export { fetchProjects, type Project } from "@/lib/stylebook-api/projects"
export {
  LOCATION_TYPES,
  type CanonicalLocation,
  type LinkedMention,
  type Location,
  type LocationMentionsResponse,
  type PaginatedCanonicalLocationResponse,
  type PaginatedLocationResponse,
  createCanonicalLocation,
  createLocation,
  deleteCanonicalLocation,
  deleteLocation,
  getCanonicalLocation,
  getCanonicalLocationMentions,
  getLocation,
  getLocationMentions,
  listCanonicalLocations,
  listLocationOptions,
  listLocations,
  patchCanonicalLocation,
  updateLocation,
  updateLocationGeometry,
} from "@/lib/stylebook-api/locations"
export {
  type AcceptCandidateBody,
  type Candidate,
  type CandidateCluster,
  type ListCandidatesFilterOptions,
  type ListClustersOptions,
  type PaginatedCandidatesResponse,
  type PaginatedClustersResponse,
  acceptCandidate,
  listCandidates,
  listClusters,
  listLocationCandidateTypes,
} from "@/lib/stylebook-api/candidates"
export {
  type AgentType,
  type EntityTypeStats,
  type Stats,
  getAgentTypes,
  getStats,
} from "@/lib/stylebook-api/stats-stub"
