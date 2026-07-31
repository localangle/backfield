import { describe, expect, it } from 'vitest'

import {
  getMiddleNodeDefaultData,
  getOutputBookendDefaultData,
} from '@/lib/flowBuilderDefaults'

describe('project Stylebook inheritance', () => {
  it('does not add a Stylebook choice to new runtime nodes', () => {
    expect(getMiddleNodeDefaultData('GeocodeAgent')).not.toHaveProperty('stylebook_id')
    expect(getMiddleNodeDefaultData('GeocodeAgent')).not.toHaveProperty('stylebookId')
    expect(getOutputBookendDefaultData('DBOutput')).not.toHaveProperty('stylebook_id')
    expect(getOutputBookendDefaultData('DBOutput')).not.toHaveProperty('stylebookId')
  })
})
