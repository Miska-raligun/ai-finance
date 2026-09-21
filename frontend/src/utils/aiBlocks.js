/** 单块 AI 生成的在途状态,放在模块级。
 *
 *  为什么不放组件里:切个 Tab、关个弹窗,组件就卸载了,请求还在飞但结果
 *  没人接——用户的感受就是"切走再回来什么都没了"。状态挂在模块上,
 *  组件只是它的一个视图,来回切不影响。
 *
 *  另外记了开始时间:这类调用动辄十几秒,只显示"生成中…"用户不知道
 *  是在跑还是卡死了,得让秒数走起来。
 */
import { reactive, computed } from 'vue'

const jobs = reactive({})          // key -> { running, error, result, startedAt, doneAt }
let ticker = null
const now = reactive({ t: Date.now() })

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
    // 跑了几秒。用一个全局 ticker 驱动,不给每个组件各起一个定时器
    elapsed: computed(() => {
      if (!j.running) return 0
      return Math.max(0, Math.round((now.t - j.startedAt) / 1000))
    }),
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

/** 轮询一个作业直到结束。 */
async function follow(key, jobId) {
  const j = slot(key)
  const { default: api } = await import('@/api')
  for (;;) {
    let job
    try {
      job = (await api.get(`/api/trips/ai/jobs/${jobId}`)).data
    } catch (e) {
      if (e?.response?.status === 404) {       // 作业没了(服务重启清过场)
        j.error = '任务丢了,再试一次'
        break
      }
      await new Promise(r => setTimeout(r, 3000))   // 网络抖动,接着等
      continue
    }
    if (job.status === 'done') {
      j.result = job.result
      break
    }
    if (job.status === 'failed' || job.status === 'cancelled') {
      j.error = job.error || '生成失败,再试一次'
      break
    }
    await new Promise(r => setTimeout(r, 1500))
  }
  j.running = false
  j.doneAt = Date.now()
  remember(key, null)
  ensureTicker()
}

/** 发起一次生成。同一个 key 已经在跑就不重复发。
 *
 *  后端是异步的:POST 只排队并立刻返回 job_id,真正的结果靠轮询取。
 *  这样任何一个 HTTP 请求都不会挂超过一秒——不然慢的时候连接要占几分钟,
 *  nginx 会判超时、连续几次还会把上游熔断成 503。
 */
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
    const { default: api } = await import('@/api')
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
