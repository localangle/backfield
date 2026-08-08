#!/usr/bin/env node
/**
 * Launch a Cursor cloud agent against localangle/backfield-docs for a SemVer release.
 *
 * Required env:
 *   CURSOR_API_KEY
 *   RELEASE_TAG          e.g. v0.8.0
 *
 * Optional env:
 *   PREVIOUS_TAG         prior SemVer tag (empty = first public baseline)
 *   COMMIT_SUMMARY       git log / subject list between tags
 *   RELEASE_NOTES        GitHub-generated release notes body
 *   RELEASE_URL          https://github.com/localangle/backfield/releases/tag/...
 *   DOCS_REPO_URL        default https://github.com/localangle/backfield-docs
 *   DOCS_STARTING_REF    default main
 *   CURSOR_MODEL         default composer-2.5
 */

import { Agent, CursorAgentError } from "@cursor/sdk"

function requiredEnv(name) {
  const value = process.env[name]
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required env ${name}`)
  }
  return value.trim()
}

function optionalEnv(name, fallback = "") {
  const value = process.env[name]
  if (typeof value !== "string") return fallback
  return value.trim()
}

function buildPrompt({
  releaseTag,
  previousTag,
  commitSummary,
  releaseNotes,
  releaseUrl,
}) {
  const previousLabel = previousTag || "(none — first public baseline or unknown prior tag)"
  return `You are updating Backfield product documentation after a SemVer release.

## Contract (must follow)
Read and obey \`docs/meta/release-update-contract.md\` in this repository before editing anything.

## Release context
- RELEASE_TAG: ${releaseTag}
- PREVIOUS_TAG: ${previousLabel}
- Backfield release URL: ${releaseUrl || "(not provided)"}

### Commit summary
\`\`\`
${commitSummary || "(not provided)"}
\`\`\`

### GitHub release notes
\`\`\`
${releaseNotes || "(not provided)"}
\`\`\`

## Your job
1. Follow the contract hard rules and path allowlist.
2. Prepend a product-facing changelog row for ${releaseTag} in \`docs/changelog.md\`.
3. Update only the existing platform/tutorial/api/support pages that must stay accurate for user-visible changes described above. Prefer omit over inventing API or UI details.
4. Open or update a pull request titled \`docs: Backfield ${releaseTag} release notes\`.
5. In the PR body include the tag, Backfield release URL, files touched, and whether this was changelog-only.
6. Do not merge the PR. Do not deploy. Do not edit files outside the allowlist.

If an open PR already exists for this tag, update that branch instead of opening a duplicate.
`
}

async function main() {
  const apiKey = requiredEnv("CURSOR_API_KEY")
  const releaseTag = requiredEnv("RELEASE_TAG")
  const previousTag = optionalEnv("PREVIOUS_TAG")
  const commitSummary = optionalEnv("COMMIT_SUMMARY")
  const releaseNotes = optionalEnv("RELEASE_NOTES")
  const releaseUrl = optionalEnv(
    "RELEASE_URL",
    `https://github.com/localangle/backfield/releases/tag/${releaseTag}`,
  )
  const docsRepoUrl = optionalEnv(
    "DOCS_REPO_URL",
    "https://github.com/localangle/backfield-docs",
  )
  const startingRef = optionalEnv("DOCS_STARTING_REF", "main")
  const modelId = optionalEnv("CURSOR_MODEL", "composer-2.5")

  const prompt = buildPrompt({
    releaseTag,
    previousTag,
    commitSummary,
    releaseNotes,
    releaseUrl,
  })

  console.log(`Launching docs sync cloud agent for ${releaseTag}`)
  console.log(`docs repo=${docsRepoUrl} startingRef=${startingRef} model=${modelId}`)

  let result
  try {
    result = await Agent.prompt(prompt, {
      apiKey,
      model: { id: modelId },
      cloud: {
        repos: [{ url: docsRepoUrl, startingRef }],
        autoCreatePR: true,
        skipReviewerRequest: true,
      },
    })
  } catch (err) {
    if (err instanceof CursorAgentError) {
      console.error(`Cursor agent failed to start: ${err.message}`)
      if (err.isRetryable) {
        console.error("Failure is marked retryable.")
      }
      process.exit(1)
    }
    throw err
  }

  console.log(`agent status=${result.status}`)
  if (result.result) {
    console.log(String(result.result).slice(0, 4000))
  }

  if (result.status === "error") {
    console.error("Cloud agent run finished with status=error")
    process.exit(2)
  }

  if (result.status !== "finished") {
    console.error(`Unexpected agent status: ${result.status}`)
    process.exit(2)
  }

  console.log("Docs sync agent finished successfully.")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
