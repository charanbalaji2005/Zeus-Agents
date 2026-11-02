import type { Usage } from '@zeus/shared/gateway-events'

export { usageFromTick } from '@zeus/shared/usage-tick'

export const ZERO: Usage = { calls: 0, input: 0, output: 0, total: 0 }
