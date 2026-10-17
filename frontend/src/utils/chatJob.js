/** 聊天类回复的前端侧:记账聊天和投资顾问共用这一份。
 *
 *  回复在后端作业里边生成边写(见 backend/routes/chat.py)。这里提交拿到
 *  job_id,然后每隔一小会儿问一次"第 N 个字之后又写了什么",拿到就追加,
 *  看起来还是一个字一个字地出来。HTTP 请求都是一瞬间的事:不占服务器的
 *  工作线程,也不会撞 Nginx / Cloudflare 的超时。
 */
import api from '@/api'

const POLL_MS = 600
const MAX_NET_ERRORS = 5          // 轮询时网络抖几下不算失败

/**
 * @param {string} url  提交地址(返回 {job_id})
 * @param {object} body
 * @param {{onStatus?: Function, onDelta?: Function, onMeta?: Function}} handlers
 *   onStatus(text)  正文出来之前的进度提示,如"正在查账…"
 *   onDelta(text)   新增的正文
 *   onMeta(obj)     附加数据(待确认卡片),可能比正文早到
 * @returns {Promise<object>} 作业结果 {reply, ...};失败时抛出带原因的 Error
 */
export async function runChatJob(url, body, handlers = {}) {
  const { job_id: jobId } = (await api.post(url, body)).data
  let received = 0
  let metaSent = false
  let netErrors = 0

  for (;;) {
    await new Promise(r => setTimeout(r, POLL_MS))
    let job
    try {
      job = (await api.get(`/api/chat/jobs/${jobId}`, { params: { since: received }, silent: true })).data
      netErrors = 0
    } catch (e) {
      if (e?.response?.status === 404) throw new Error('任务已失效（可能服务刚重启），请重新发送')
      if (++netErrors >= MAX_NET_ERRORS) throw new Error('网络不稳定，没能拿到回复，请稍后再试')
      continue
    }

    if (job.length > received) {
      handlers.onDelta?.(job.text)
      received = job.length
    } else if (job.step && !received) {
      handlers.onStatus?.(job.step)
    }
    if (!metaSent && job.meta && Object.keys(job.meta).length) {
      handlers.onMeta?.(job.meta)
      metaSent = true
    }

    if (job.status === 'done') return job.result || {}
    if (job.status === 'failed') throw new Error(job.error || '生成失败，请稍后再试')
    if (job.status === 'cancelled') throw new Error('已取消')
  }
}
