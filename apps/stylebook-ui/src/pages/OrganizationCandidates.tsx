import { CandidateQueuePage } from "@/components/CandidateQueuePage"
import { organizationCandidateQueueConfig } from "@/lib/entityConfigs/organization/candidateQueue"

export default function OrganizationCandidates() {
  return <CandidateQueuePage config={organizationCandidateQueueConfig} />
}
