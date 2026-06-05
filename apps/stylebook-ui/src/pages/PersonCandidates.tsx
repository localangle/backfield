import { CandidateQueuePage } from "@/components/CandidateQueuePage"
import { personCandidateQueueConfig } from "@/lib/entityConfigs/person/candidateQueue"

export default function PersonCandidates() {
  return <CandidateQueuePage config={personCandidateQueueConfig} />
}
