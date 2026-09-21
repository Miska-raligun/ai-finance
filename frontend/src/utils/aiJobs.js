/** 后台 AI 作业的前端侧:提交 → 轮询 → 拿结果。
 *
 *  后端所有耗时的 LLM 端点都是"POST 只排队并立刻返回 job_id,结果轮询取"。
 *  同步的话 HTTP 连接要挂几分钟,会踩 nginx 超时 / 熔断和 waitress 线程占满。
 *
 *  这里有两种用法,共用同一套轮询:
 *    * runAiJob(url, body)  —— await 到结果。适合弹窗里等着的场景。
 *    * runAiBlock(key, ...) —— 不等,状态挂在模块级 store 上。适合"点了就
 *      可以切走"的场景:切个 Tab、关个弹窗组件就卸载了,请求还在飞但结果
 *      没人接——用户的感受就是"切走再回来什么都没了"。
 */
import { reactive, computed } from 'vue'
import api from '@/api'

const POLL_MS = 1200

/** 轮询一个作业到终态,返回后端那条作业记录。 */
async function pollJob(jobId, { signal, interval = POLL_MS, onTick } = {}) {
  for (;;) {
    if (signal?.aborted) {
      const err = new Error('canceled')
      err.name = 'CanceledError'
      throw err
    }
    const job = (await api.get(`/api/ai-jobs/${jobId}`, { signal })).data
    onTick?.(job)
    if (job.status === 'done' || job.status === 'failed' || job.status === 'cancelled') {
      return job
    }
    await new Promise(r => setTimeout(r, interval))
  }
}

/**
 * 提交一个作业并等结果。
 * @param {string} url 业务端点(它返回 {job_id})
 * @param {object} body
 * @param {{signal?: AbortSignal, interval?: number}} opts
 * @returns {Promise<object>} 作业的 result
 */
export async function runAiJob(url, body, opts = {}) {
  const { job_id: jobId } = (await api.post(url, body, { signal: opts.signal })).data
  const job = await pollJob(jobId, opts)
  if (job.status !== 'done') throw new Error(job.error || '生成失败，请稍后再试')
  return job.result
}

// ---------- 不等结果的那种:状态挂模块级 ----------

// key -> { running, error, result, startedAt, doneAt }
const jobs = reactive({})
let ticker = null
const now = reactive({ t: Date.now() })

// 这类调用动辄十几秒,只显示"生成中…"用户不知道是在跑还是卡死了,
// 得让秒数走起来。一个全局 ticker 驱动所有组件,不各起各的定时器。
function ensureTicker() {
  const anyRunning = Object.values(jobs).some(j => j.running)
  if (anyRunning && !ticker) {
    ticker = setInterval(() => { now.t = Date.now() }, 500)
  } else if (!anyRunning && ticker) {
    clearInterval(ticker)
    ticker = null
  }
}

function slot(key) {
  if (!jobs[key]) {
    jobs[key] = { running: false, error: '', result: null, startedAt: 0, doneAt: 0 }
  }
  return jobs[key]
}

/** 组件里这样用:const job = useAiBlock('packing:12') */
export function useAiBlock(key) {
  const j = slot(key)
  return {
    state: j,
    elapsed: computed(() => (j.running ? Math.max(0, Math.round((now.t - j.startedAt) / 1000)) : 0)),
  }
}

/** key 会变的场景(比如地图弹窗切景点)直接用这两个,
 *  不要在 computed 里反复 useAiBlock —— 那样每次求值都会新建一个 computed。 */
export function aiState(key) {
  return slot(key)
}

export function aiElapsed(key) {
  const j = jobs[key]
  if (!j || !j.running) return 0
  return Math.max(0, Math.round((now.t - j.startedAt) / 1000))
}

const RESUME_KEY = 'trip:aiblocks'

/** 在途的 job id 存一份到 localStorage:刷新页面也能接回来。 */
function remember(key, jobId) {
  try {
    const all = JSON.parse(localStorage.getItem(RESUME_KEY) || '{}')
    if (jobId) all[key] = jobId
    else delete all[key]
    localStorage.setItem(RESUME_KEY, JSON.stringify(all))
  } catch { /* 隐私模式下会抛 */ }
}

function remembered() {
  try {
    return JSON.parse(localStorage.getItem(RESUME_KEY) || '{}')
  } catch {
    return {}
  }
}

async function follow(key, jobId) {
  const j = slot(key)
  for (;;) {
    let job
    try {
      job = await pollJob(jobId, { interval: 1500 })
    } catch (e) {
      if (e?.response?.status === 404) {       // 作业没了(服务重启清过场)
        j.error = '任务丢了,再试一次'
        break
      }
      await new Promise(r => setTimeout(r, 3000))   // 网络抖动,接着等
      continue
    }
    if (job.status === 'done') j.result = job.result
    else j.error = job.error || '生成失败,再试一次'
    break
  }
  j.running = false
  j.doneAt = Date.now()
  remember(key, null)
  ensureTicker()
}

/** 发起一次生成,不等结果。同一个 key 已经在跑就不重复发。 */
export async function runAiBlock(key, url, body) {
  const j = slot(key)
  if (j.running) return
  j.running = true
  j.error = ''
  j.result = null
  j.startedAt = Date.now()
  ensureTicker()
  let jobId
  try {
    jobId = (await api.post(url, body)).data.job_id
  } catch (e) {
    j.error = e?.response?.data?.error || '提交失败,再试一次'
    j.running = false
    ensureTicker()
    return
  }
  remember(key, jobId)
  follow(key, jobId)        // 不 await:调用方不该被这一等卡住
}

/** 页面加载时把刷新前还在跑的任务接回来。 */
export function resumeAiBlocks() {
  for (const [key, jobId] of Object.entries(remembered())) {
    const j = slot(key)
    if (j.running) continue
    j.running = true
    j.error = ''
    j.result = null
    j.startedAt = Date.now()
    ensureTicker()
    follow(key, jobId)
  }
}

/** 结果被组件消费掉之后清掉,免得下次挂载又弹出来一份旧的。 */
export function clearAiBlock(key) {
  const j = jobs[key]
  if (j) { j.result = null; j.error = '' }
}
