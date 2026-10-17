/** 聊天类接口的流式客户端:记账聊天和投资顾问共用这一份。
 *
 *  后端格式见 backend/services/sse.py:每个事件一行 `data: {json}`,事件间空一行,
 *  最后 `data: [DONE]`;`: ping` 这种注释行是心跳,直接忽略。
 *
 *    {delta}   正文增量      → onDelta(text)
 *    {status}  进度提示      → onStatus(text)
 *    {meta}    附加数据      → onMeta(obj)(比如待确认卡片)
 *    {error}   出错说明      → onError(text)
 */
import { getCsrfToken, CSRF_HEADER } from '@/api'

/**
 * @param {string} url
 * @param {object} body
 * @param {{onDelta?: Function, onStatus?: Function, onMeta?: Function, onError?: Function}} handlers
 * @returns {Promise<string>} 拼好的完整正文
 */
export async function streamChat(url, body, handlers = {}) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', [CSRF_HEADER]: getCsrfToken() },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    let msg = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      msg = data.error || data.message || msg
    } catch { /* 不是 JSON(比如网关的错误页) */ }
    throw new Error(msg)
  }

  const decoder = new TextDecoder()   // stream:true 处理被切开的多字节汉字
  const reader = res.body.getReader()
  let buffer = ''
  let text = ''

  const handle = (block) => {
    const line = block.trim()
    if (!line.startsWith('data:')) return false          // 心跳 / 空行
    const payload = line.slice(5).trim()
    if (payload === '[DONE]') return true
    let ev
    try { ev = JSON.parse(payload) } catch { return false }
    if (ev.delta) { text += ev.delta; handlers.onDelta?.(ev.delta) }
    if (ev.status) handlers.onStatus?.(ev.status)
    if (ev.meta) handlers.onMeta?.(ev.meta)
    if (ev.error) handlers.onError?.(ev.error)
    return false
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop()            // 最后一段可能只收到一半,留到下一轮
    for (const b of blocks) {
      if (handle(b)) { reader.cancel().catch(() => {}); return text }
    }
  }
  if (buffer) handle(buffer)
  return text
}
