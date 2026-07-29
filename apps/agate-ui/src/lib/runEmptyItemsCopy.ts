import type { Run, S3BatchSummary } from '@/lib/api'

export type RunEmptyItemsCopy = {
  title: string
  description: string
}

export function s3BatchAlreadyProcessedCount(
  s3Batch: S3BatchSummary | null | undefined,
): number {
  if (!s3Batch) return 0
  return Math.max(0, Number(s3Batch.skipped_unchanged) || 0)
}

/** Empty-state copy when a finished run has zero processed items. */
export function runEmptyItemsCopy(run: Pick<Run, 'status' | 's3_batch'>): RunEmptyItemsCopy {
  const alreadyProcessed = s3BatchAlreadyProcessedCount(run.s3_batch)
  const finished =
    run.status === 'completed' || run.status === 'completed_with_errors'

  if (finished && alreadyProcessed > 0) {
    return {
      title: 'Nothing new to process',
      description:
        alreadyProcessed === 1
          ? 'The file in this folder was already processed successfully. Turn on “Process files again” in S3 Input if you want to run it once more.'
          : `All ${alreadyProcessed} files in this folder were already processed successfully. Turn on “Process files again” in S3 Input if you want to run them again.`,
    }
  }

  if (finished && run.s3_batch && run.s3_batch.total_json_objects > 0) {
    return {
      title: 'Nothing new to process',
      description:
        'No new files were ready to run in this folder. Turn on “Process files again” in S3 Input if you want to re-run files that already completed.',
    }
  }

  return {
    title: 'No Items Processed',
    description: 'This run has no processed items yet.',
  }
}
