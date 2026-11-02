import { vi } from 'vitest'

import type { ZeusApiRequest } from '@/global'

/** Install a fake `window.zeusDesktop.api`, the preload bridge every REST helper sends through. */
export function installRestBridge(answer: (request: ZeusApiRequest) => object) {
  const api = vi.fn(async (request: ZeusApiRequest) => answer(request))

  Object.defineProperty(window, 'zeusDesktop', { configurable: true, value: { api } })

  return api
}
