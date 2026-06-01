/**
 * 极简事件总线，给跨 store / 跨 view 的数据失效通知用。
 *
 * 为什么不上 mitt：仅需 20 行就能解决，少一个外部依赖；API 一致（on/off/emit）。
 *
 * 约定的事件名（写一处 emit 即可让多处监听者刷新）：
 *   data:records   — records 表 CRUD 后
 *   data:income    — income 表 CRUD 后
 *   data:budgets   — budgets 表 CRUD 后
 *   data:assets    — assets 表 CRUD 后
 *   data:goals     — financial_goals 表 CRUD 后
 *
 * 监听方一般把对应 store 的 `stale = true`，由 view 在 `onActivated` 时拉一次新数据。
 */

const subs = new Map()

export function on(event, handler) {
  if (!subs.has(event)) subs.set(event, new Set())
  subs.get(event).add(handler)
  // 返回解绑函数，方便 `onBeforeUnmount(() => off())`。
  return () => subs.get(event)?.delete(handler)
}

export function off(event, handler) {
  subs.get(event)?.delete(handler)
}

export function emit(event, payload) {
  const handlers = subs.get(event)
  if (!handlers) return
  for (const h of handlers) {
    try { h(payload) } catch (e) { console.error('[event-bus]', event, e) }
  }
}

export default { on, off, emit }
