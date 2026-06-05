import { CandidateQueuePage } from "@/components/CandidateQueuePage"
import { locationCandidateQueueConfig } from "@/lib/entityConfigs/location/candidateQueue"

export default function LocationCandidates() {
  return <CandidateQueuePage config={locationCandidateQueueConfig} />
}
