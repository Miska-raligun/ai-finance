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

/** 发起一次生成。同一个 key 已经在跑就不重复发。
 *  @returns {Promise<object|null>} 成功给结果,失败给 null(错误在 state.error 里) */
export async function runAiBlock(key, url, body) {
  const j = slot(key)
  if (j.running) return null
  j.running = true
  j.error = ''
  j.result = null
  j.startedAt = Date.now()
  ensureTicker()
  try {
    const { default: api } = await import('@/api')
    const res = await api.post(url, body)
    j.result = res.data
    return res.data
  } catch (e) {
    j.error = e?.response?.data?.error
      || (e?.code === 'ECONNABORTED' ? '生成超时了,再试一次' : '生成失败,再试一次')
    return null
  } finally {
    j.running = false
    j.doneAt = Date.now()
    ensureTicker()
  }
}

/** 结果被组件消费掉之后清掉,免得下次挂载又弹出来一份旧的。 */
export function clearAiBlock(key) {
  const j = jobs[key]
  if (j) { j.result = null; j.error = '' }
}
