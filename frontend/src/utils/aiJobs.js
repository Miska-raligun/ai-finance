/** 单次 AI 作业的轮询。
 *
 *  财务体检、买之前问一下这类端点现在是"提交即返回 job_id,结果轮询取"。
 *  同步的话 HTTP 连接要挂几分钟,会踩 nginx 超时 / 熔断和 waitress 线程占满。
 */
import api from '@/api'

/**
 * 提交一个作业并等结果。
 * @param {string} url 业务端点(它返回 {job_id})
 * @param {object} body
 * @param {{signal?: AbortSignal, interval?: number}} opts
 * @returns {Promise<object>} 作业的 result
 */
export async function runAiJob(url, body, opts = {}) {
  const { signal, interval = 1200 } = opts
  const { job_id: jobId } = (await api.post(url, body, { signal })).data
  for (;;) {
    if (signal?.aborted) {
      const err = new Error('canceled')
      err.name = 'CanceledError'
      throw err
    }
    const job = (await api.get(`/api/ai-jobs/${jobId}`, { signal })).data
    if (job.status === 'done') return job.result
    if (job.status === 'failed') {
      throw new Error(job.error || '生成失败，请稍后再试')
    }
    await new Promise(r => setTimeout(r, interval))
  }
}
