import { describe, expect, it } from 'vitest'
import {
  connectionsStatusLabel,
  formatConnectionsDetail,
  normalizeProcessedItemConnections,
  shouldShowConnectionsSummary,
} from './connectionsDisplay'

describe('connectionsDisplay helpers', () => {
  it('normalizes created edges from API summary', () => {
    const summary = normalizeProcessedItemConnections({
      status: 'succeeded',
      enabled: true,
      created_count: 1,
      edges: [
        {
          from_display_name: 'Jane Smith',
          to_display_name: 'Chicago City Hall',
          nature: 'works_for',
          confidence: 0.95,
        },
      ],
      error: null,
    })
    expect(summary.status).toBe('succeeded')
    expect(summary.created_count).toBe(1)
    expect(summary.edges[0]?.nature).toBe('works_for')
  })

  it('shows summary when enabled or ineligible', () => {
    expect(
      shouldShowConnectionsSummary(
        normalizeProcessedItemConnections({ status: 'disabled', enabled: false }),
      ),
    ).toBe(false)
    expect(
      shouldShowConnectionsSummary(
        normalizeProcessedItemConnections({ status: 'ineligible', enabled: true }),
      ),
    ).toBe(true)
  })

  it('formats succeeded summary as a created count only', () => {
    const detail = formatConnectionsDetail(
      normalizeProcessedItemConnections({
        status: 'succeeded',
        enabled: true,
        created_count: 3,
        edges: [
          {
            from_display_name: 'Jane Smith',
            to_display_name: 'Chicago City Hall',
            nature: 'works_for',
            confidence: 0.95,
          },
        ],
      }),
    )
    expect(detail).toBe('3 connections created')
  })

  it('labels failed status', () => {
    expect(connectionsStatusLabel('failed')).toBe('Failed')
  })
})
