/** 聊天里 AI 识别出来的"待确认卡片"(投资资产 / 理财目标),两个聊天框共用。
 *  记账那种卡片的确认逻辑只在记账聊天里有,留在 ChatView。 */
import { ElMessage } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'

const KINDS = ['pending_records', 'pending_assets', 'pending_goals']

/** 把后端给的待确认列表挂到消息上,每张卡带上编辑态 */
export function decoratePending(data, msg) {
  for (const k of KINDS) {
    if (data?.[k]?.length) {
      msg[k] = data[k].map(rec => ({ ...rec, _state: 'pending', _edit: { ...rec } }))
    }
  }
}

export function usePendingCards() {
  const store = useInvestmentStore()

  async function commit(rec, fn, okText) {
    rec._state = 'saving'
    rec._error = ''
    try {
      const res = await fn({ ...rec._edit })
      if (res?.success) {
        rec._state = 'confirmed'
        ElMessage.success(okText)
      } else {
        rec._state = 'error'
        rec._error = res?.message || '入库失败'
      }
    } catch (e) {
      rec._state = 'error'
      rec._error = e?.response?.data?.message || e?.response?.data?.error || '网络异常'
    }
  }

  return {
    confirmAsset: (rec) => commit(rec, store.commitPendingAsset, '已添加到投资理财'),
    confirmGoal: (rec) => commit(rec, store.commitPendingGoal, '已添加理财目标'),
  }
}
