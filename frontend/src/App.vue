<!-- src/App.vue -->
<template>
  <!-- 全局 SVG defs：Animal Island Modal 有机 blob clip-path -->
  <svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
    <defs>
      <clipPath id="animal-modal-clip" clipPathUnits="objectBoundingBox">
        <path d="M0.501,0.005 L0.523,0.005 L0.549,0.006 C0.704,0.01,0.796,0.017,0.825,0.027 L0.827,0.028 C0.872,0.045,0.939,0.044,0.978,0.17 C1,0.254,1,0.365,0.99,0.505 L0.988,0.513 C0.979,0.558,0.971,0.598,0.965,0.633 C0.956,0.689,0.979,0.77,0.964,0.865 C0.953,0.928,0.921,0.966,0.869,0.979 C0.821,0.986,0.773,0.992,0.726,0.995 L0.712,0.996 L0.694,0.997 C0.648,1,0.586,1,0.507,1 L0.501,1 L0.464,1 C0.385,1,0.325,0.998,0.283,0.995 C0.234,0.992,0.184,0.987,0.133,0.979 C0.081,0.966,0.05,0.928,0.039,0.865 C0.023,0.77,0.047,0.689,0.037,0.633 C0.031,0.595,0.023,0.552,0.013,0.505 C-0.006,0.365,-0.002,0.254,0.024,0.17 C0.064,0.045,0.13,0.045,0.174,0.028 L0.175,0.028 C0.204,0.017,0.303,0.009,0.474,0.005 L0.501,0.005"/>
      </clipPath>
    </defs>
  </svg>

  <el-container style="height: 100vh; height: 100dvh">
    <!-- PC 侧边栏 -->
    <el-aside v-if="!isMobile && route.path !== '/login'" width="220px" class="app-aside">
      <div class="brand brand-link" role="button" title="回到首页" @click="router.push('/home')">
        <img src="@/assets/decor/tree.svg" class="brand-tree" alt="" aria-hidden="true">
        <span class="brand-name">智能记账</span>
      </div>
      <nav class="side-nav" aria-label="主导航">
        <router-link to="/home" class="nav-item" :class="{ active: route.path === '/home' }" :aria-current="route.path === '/home' ? 'page' : null">
          <img src="@/assets/decor/tree.svg" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 首页
        </router-link>
        <router-link to="/chat" class="nav-item" :class="{ active: route.path === '/chat' }" :aria-current="route.path === '/chat' ? 'page' : null">
          <img :src="iconBunny" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 聊天记账
        </router-link>
        <router-link to="/ledger" class="nav-item" :class="{ active: route.path === '/ledger' }" :aria-current="route.path === '/ledger' ? 'page' : null">
          <img :src="iconShiba" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 账本管理
        </router-link>
        <router-link to="/investment" class="nav-item" :class="{ active: route.path === '/investment' }" :aria-current="route.path === '/investment' ? 'page' : null">
          <img :src="iconOwl" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 投资理财
        </router-link>
        <router-link to="/reports" class="nav-item" :class="{ active: route.path === '/reports' }" :aria-current="route.path === '/reports' ? 'page' : null">
          <img :src="iconBeaver" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 月度报告
        </router-link>
        <router-link v-if="isAdmin" to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }" :aria-current="route.path === '/admin' ? 'page' : null">
          <img :src="iconFox" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 用户管理
        </router-link>
      </nav>

      <!-- 中间装饰：Anon 提示卡（点头像换一句）+ 实时时钟
           填充 nav 与 footer 之间的视觉空白 -->
      <div class="side-mid">
        <div class="side-tip">
          <img
            src="/favicon.ico"
            class="side-tip-avatar"
            :class="{ 'is-loading': tipLoading }"
            alt="点击换一句"
            title="点击让 Anon 换一句"
            @click="refreshTip"
          >
          <div class="side-tip-bubble">
            <div class="side-tip-text">{{ tip }}</div>
          </div>
        </div>
        <div class="side-clock" aria-hidden="true">
          <span class="clock-time">{{ clockTime }}</span>
          <span class="clock-date">{{ clockDate }}</span>
        </div>
      </div>

      <div class="side-footer">
        <div class="user-info">
          <div class="user-avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
          <div class="user-name">{{ username }}</div>
        </div>
        <div class="side-actions">
          <button class="side-btn primary" @click="showDecisionHelper = true">💭 买之前问一下</button>
          <button class="side-btn" @click="showCheckup = true">🩺 财务体检</button>
          <button class="side-btn" @click="showThemePicker = true">🎨 主题</button>
          <button class="side-btn" @click="openConfigPanel">⚙️ 模型配置</button>
          <button class="side-btn danger" @click="logout">🚪 退出登录</button>
        </div>
        <!-- 海浪条带：sidebar 底部装饰 -->
        <div class="side-wave" aria-hidden="true"></div>
      </div>
    </el-aside>

    <!-- 移动端侧边抽屉 -->
    <el-drawer
      v-if="isMobile && route.path !== '/login'"
      v-model="showDrawer"
      :with-header="false"
      size="240px"
      class="mobile-drawer"
      direction="ltr"
    >
      <div class="app-aside drawer-inner">
        <div class="brand">
          <img src="@/assets/decor/tree.svg" class="brand-tree" alt="" aria-hidden="true">
          <span class="brand-name">智能记账</span>
        </div>
        <nav class="side-nav">
          <router-link to="/home" class="nav-item" :class="{ active: route.path === '/home' }" @click="showDrawer=false">
            <img src="@/assets/decor/tree.svg" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 首页
          </router-link>
          <router-link to="/chat" class="nav-item" :class="{ active: route.path === '/chat' }" @click="showDrawer=false">
            <img :src="iconBunny" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 聊天记账
          </router-link>
          <router-link to="/ledger" class="nav-item" :class="{ active: route.path === '/ledger' }" @click="showDrawer=false">
            <img :src="iconShiba" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 账本管理
          </router-link>
          <router-link to="/investment" class="nav-item" :class="{ active: route.path === '/investment' }" @click="showDrawer=false">
            <img :src="iconOwl" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 投资理财
          </router-link>
          <router-link to="/reports" class="nav-item" :class="{ active: route.path === '/reports' }" @click="showDrawer=false">
            <img :src="iconBeaver" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 月度报告
          </router-link>
          <router-link v-if="isAdmin" to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }" @click="showDrawer=false">
            <img :src="iconFox" class="nav-icon nav-avatar" alt="" aria-hidden="true"> 用户管理
          </router-link>
        </nav>

        <!-- 中间装饰：与 PC sidebar 一致 -->
        <div class="side-mid" aria-hidden="true">
          <div class="side-tip">
            <img src="/favicon.ico" class="side-tip-avatar" alt="" @click="refreshTip">
            <div class="side-tip-bubble">
              <div class="side-tip-text">{{ tip }}</div>
            </div>
          </div>
          <div class="side-clock">
            <span class="clock-time">{{ clockTime }}</span>
            <span class="clock-date">{{ clockDate }}</span>
          </div>
        </div>

        <div class="side-footer">
          <div class="user-info">
            <div class="user-avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
            <div class="user-name">{{ username }}</div>
          </div>
          <div class="side-actions">
            <button class="side-btn" @click="showThemePicker = true; showDrawer=false">🎨 主题</button>
            <button class="side-btn" @click="openConfigPanel(); showDrawer=false">⚙️ 模型配置</button>
            <button class="side-btn danger" @click="logout">🚪 退出登录</button>
          </div>
          <div class="side-wave" aria-hidden="true"></div>
        </div>
      </div>
    </el-drawer>

    <el-container style="flex-direction: column; overflow: hidden; min-width: 0;">
      <!-- 移动端顶部导航栏 -->
      <header v-if="isMobile && route.path !== '/login'" class="mobile-topbar">
        <button class="topbar-menu-btn" @click="showDrawer = true" aria-label="打开菜单">☰</button>
        <span class="topbar-title">{{ topbarTitle }}</span>
        <button
          class="topbar-decide-btn checkup"
          @click="showCheckup = true"
          aria-label="财务体检"
          title="财务体检"
        >🩺</button>
        <button
          class="topbar-decide-btn"
          @click="showDecisionHelper = true"
          aria-label="买之前问一下"
          title="买之前问一下"
        >💭</button>
        <div class="topbar-user">{{ username.slice(0, 1).toUpperCase() }}</div>
      </header>

      <el-main :class="{ 'has-topbar': isMobile && route.path !== '/login' }">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in" appear>
            <keep-alive :max="3">
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </transition>
        </router-view>

        <!-- LLM 配置弹窗 -->
        <el-dialog v-model="showConfig" title="⚙ LLM 配置" width="460px">
          <el-form label-width="100px" autocomplete="off">
            <el-form-item label="服务商">
              <el-select v-model="llmProvider" style="width: 100%" @change="onProviderChange">
                <el-option
                  v-for="p in providerOptions"
                  :key="p.value"
                  :value="p.value"
                  :label="p.label"
                />
              </el-select>
              <div class="provider-hint">{{ activeProviderDesc }}</div>
            </el-form-item>
            <el-form-item label="API URL">
              <el-input v-model="llmUrl" :placeholder="urlPlaceholder" autocomplete="off" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmKey" type="password" show-password autocomplete="new-password" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="llmModel" :placeholder="modelPlaceholder" autocomplete="off" />
            </el-form-item>
            <el-form-item label="角色人设">
              <el-input v-model="llmPersona" type="textarea" :rows="2" placeholder="一个有点傲娇的财务顾问" autocomplete="off" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="useDefault">加载系统默认</el-button>
            <el-button type="primary" @click="saveConfig">保存配置</el-button>
          </template>
        </el-dialog>

        <!-- 主题切换器 -->
        <ThemePicker v-model="showThemePicker" />

        <!-- 决策助手：买之前问一下 -->
        <DecisionHelper v-model="showDecisionHelper" />

        <!-- 财务体检：健康分 + 四维 + 趋势 -->
        <FinancialCheckup v-model="showCheckup" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { ref, computed, watchEffect, onMounted, watch, onBeforeUnmount, onErrorCaptured, defineAsyncComponent } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import bus from '@/event-bus'
// 原创小动物头像 — 替代 sidebar nav 与 Phone 磁贴的 emoji，避免任天堂版权问题
import iconBunny from '@/assets/decor/avatars/bunny.svg'
import iconShiba from '@/assets/decor/avatars/shiba.svg'
import iconOwl from '@/assets/decor/avatars/owl.svg'
import iconBeaver from '@/assets/decor/avatars/beaver.svg'
import iconFox from '@/assets/decor/avatars/fox.svg'
import ThemePicker from '@/components/ThemePicker.vue'
import DecisionHelper from '@/components/DecisionHelper.vue'
// FinancialCheckup 自带 ECharts 仪表 + 折线，挂在全局 App.vue 里会拖首屏。
// 改成异步组件——只有用户点「🩺 财务体检」按钮 v-model 切到 true 时才网络拉。
const FinancialCheckup = defineAsyncComponent(() => import('@/components/FinancialCheckup.vue'))

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { isAdmin } = storeToRefs(userStore)

const username = computed(() => userStore.username)
const topbarTitle = computed(() => {
  const map = {
    '/chat': '聊天记账',
    '/ledger': '账本管理',
    '/investment': '投资理财',
    '/reports': '月度报告',
    '/admin': '用户管理',
  }
  return map[route.path] || '智能记账'
})

const active = ref(route.path)
const showConfig = ref(false)
const showThemePicker = ref(false)
const showDecisionHelper = ref(false)
const showCheckup = ref(false)
const llmUrl = ref('')
const llmKey = ref('')
const llmModel = ref('')
const llmPersona = ref('')
const llmProvider = ref('openai')

// 三大 provider 协议族 + 常用预设。选择时自动填默认 url / model 提示。
const providerOptions = [
  { value: 'openai', label: 'OpenAI 兼容（DeepSeek / SiliconFlow / Qwen / Kimi / 智谱 / Ollama）',
    desc: '走 /chat/completions 协议；URL 填到 /chat/completions 完整地址。',
    urlExample: 'https://api.siliconflow.cn/v1/chat/completions',
    modelExample: 'Pro/deepseek-ai/DeepSeek-V3' },
  { value: 'anthropic', label: 'Anthropic Claude',
    desc: 'Claude Messages API（自动补全 /v1/messages）。',
    urlExample: 'https://api.anthropic.com',
    modelExample: 'claude-sonnet-4-5' },
  { value: 'gemini', label: 'Google Gemini',
    desc: 'generateContent API；API Key 通过 query 参数注入。',
    urlExample: 'https://generativelanguage.googleapis.com',
    modelExample: 'gemini-2.5-flash' },
]
const activeProvider = computed(
  () => providerOptions.find(p => p.value === llmProvider.value) || providerOptions[0],
)
const activeProviderDesc = computed(() => activeProvider.value.desc)
const urlPlaceholder = computed(() => activeProvider.value.urlExample)
const modelPlaceholder = computed(() => activeProvider.value.modelExample)

function onProviderChange() {
  // 切换 provider 时如果当前 url / model 是空或别家的预设，刷成新预设占位
  const p = activeProvider.value
  if (!llmUrl.value || providerOptions.some(o => llmUrl.value === o.urlExample)) {
    llmUrl.value = p.urlExample
  }
  if (!llmModel.value || providerOptions.some(o => llmModel.value === o.modelExample)) {
    llmModel.value = p.modelExample
  }
}
const isMobile = ref(window.innerWidth < 768)
const showDrawer = ref(false)

function updateIsMobile() {
  isMobile.value = window.innerWidth < 768
}
// 防抖：resize 触发频率极高，原始监听会让 ECharts 等组件被反复 resize。
// 拖动窗口时延迟 150ms 仅响应最后一次。
let _resizeTimer = null
function onResize() {
  if (_resizeTimer) clearTimeout(_resizeTimer)
  _resizeTimer = setTimeout(updateIsMobile, 150)
}
onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (_resizeTimer) clearTimeout(_resizeTimer)
})

watchEffect(() => { active.value = route.path })

onMounted(() => userStore.fetchMe())
watch(() => route.path, () => userStore.fetchMe())

// 未配置 LLM 不再强弹模态框拦路(首页会显示温和的提示条,见 HomeView);
// 这里只监听提示条/其它入口发来的打开请求。
onMounted(() => bus.on('open-llm-config', openConfigPanel))
onBeforeUnmount(() => bus.off('open-llm-config', openConfigPanel))

// ===== Sidebar 中间装饰：实时时钟 + LLM 生成的随机小贴士 =====
const _now = ref(new Date())
let _clockTimer = null
const clockTime = computed(() => {
  const d = _now.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})
const clockDate = computed(() => {
  const d = _now.value
  const w = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1}/${d.getDate()} 周${w[d.getDay()]}`
})

// tip 由后端 /api/anon/tip 异步生成；点头像 refreshTip() 重新请求
import api from '@/api'
const tip = ref('Anon 正在想小贴士…')
const tipLoading = ref(false)
async function refreshTip() {
  if (tipLoading.value) return
  tipLoading.value = true
  try {
    const res = await api.get('/api/anon/tip', { silent: true })
    if (res.data?.tip) tip.value = res.data.tip
  } catch {
    // 拦截器已显示错误；保留旧文案不替换
  } finally {
    tipLoading.value = false
  }
}

onMounted(() => {
  _clockTimer = setInterval(() => { _now.value = new Date() }, 30_000)
  // 首次进入页面 + 用户名就绪时拉一句
  if (userStore.username) refreshTip()
})
// 用户登录后再拉
watch(() => userStore.username, (v) => { if (v) refreshTip() })

onBeforeUnmount(() => {
  if (_clockTimer) clearInterval(_clockTimer)
})

async function saveConfig() {
  await userStore.saveLlmConfig({
    url: llmUrl.value,
    apikey: llmKey.value,
    model: llmModel.value,
    persona: llmPersona.value,
    provider: llmProvider.value,
  })
  showConfig.value = false
}
async function useDefault() {
  await userStore.useDefaultLlm()
  showConfig.value = false
}
async function logout() {
  await userStore.logout()
  router.push('/login')
}
function openConfigPanel() {
  // 把 store / localStorage 里已存的配置回填到表单，避免每次都从空开始
  const cfg = userStore.llmPayload
  if (cfg && typeof cfg === 'object') {
    llmProvider.value = cfg.provider || 'openai'
    llmUrl.value = cfg.url || ''
    llmKey.value = cfg.apikey || ''
    llmModel.value = cfg.model || ''
    llmPersona.value = cfg.persona || ''
  } else if (!llmUrl.value && !llmModel.value) {
    // 首次打开：填默认 provider 的占位
    onProviderChange()
  }
  showConfig.value = true
}

// 全局错误边界：捕获子组件渲染/生命周期里未处理的异常，转 toast。
// 避免页面整块白屏。仅 dev 时弹出详情，线上只露简短提示并打 console。
onErrorCaptured((err, _instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[Vue ErrorBoundary]', info, err)
  const msg = (err && err.message) || '页面出现了一个错误，请刷新或重新登录'
  try { ElMessage.error(msg.length > 120 ? msg.slice(0, 120) + '…' : msg) } catch {}
  // 返回 false 阻止继续向上传播，避免被 unhandledrejection 重复提示
  return false
})

if (typeof window !== 'undefined') {
  // Promise 链中未 catch 的错误（比如 axios reject 没处理）兜底
  window.addEventListener('unhandledrejection', (e) => {
    const reason = e?.reason
    // axios 失败已经走 api.js 拦截器 toast 过；这里只对未捕获的纯错误做兜底
    if (reason && !reason.config) {
      // eslint-disable-next-line no-console
      console.warn('[unhandledrejection]', reason)
    }
  })
}
</script>

<style>
/* ===== 全局 CSS 变量（Animal Island 设计令牌） =====
   暖米底 + 薄荷青 + 棕褐文字；Pill 圆角 + 3D 偏移阴影。 */
:root {
  /* 背景 / 表面 */
  --color-bg: #f8f8f0;
  --color-surface: rgb(247, 243, 223);
  --color-surface-2: #f0ece2;
  /* 文字 */
  --color-text: #725d42;
  --color-text-strong: #794f27;
  --color-text-muted: #9f927d;
  --color-text-disabled: #c4b89e;
  /* 薄荷青强调 */
  --color-primary: #19c8b9;
  --color-primary-dark: #11a89b;
  --color-primary-hover: #3dd4c6;
  --color-primary-light: #e6f9f6;
  /* 沙边 */
  --color-border: #c4b89e;
  --color-border-light: #d4c9b4;
  /* 状态色（动森色板） */
  --color-success: #6fba2c;
  --color-success-active: #5a9e1e;
  --color-warning: #f5c31c;
  --color-warning-active: #dba90e;
  --color-error: #e05a5a;
  --color-error-active: #c94444;
  --color-focus: #ffcc00;
  --color-focus-active: #e0b800;
  /* 涨/盈红 跌/亏绿 — WCAG AA 合规深色，不被薄荷主色覆盖 */
  --color-up: #DC2626;
  --color-down: #15803D;
  /* 3D 偏移阴影锚色 */
  --shadow-anchor: #bdaea0;
  --shadow-anchor-light: #d4c9b4;
  /* 卡片柔阴影 */
  --shadow-card: 0 4px 10px rgba(107, 92, 67, 0.18);
  --shadow-card-hover: 0 8px 24px rgba(114, 93, 66, 0.22);
  /* 圆角 */
  --radius-pill: 50px;
  --radius-card: 20px;
  --radius-card-organic: 40px 35px 45px 38px / 38px 45px 35px 40px;
  --radius-tile: 12px;
  --radius-tile-large: 45px;
  /* 布局 */
  --topbar-height: 56px;

  /* === 映射到 Element Plus 内部 CSS 变量，避免逐组件 override === */
  --el-color-primary: var(--color-primary);
  --el-color-primary-light-3: #4cd4c7;
  --el-color-primary-light-5: #80dfd6;
  --el-color-primary-light-7: #b3eae3;
  --el-color-primary-light-8: #cbf0eb;
  --el-color-primary-light-9: var(--color-primary-light);
  --el-color-primary-dark-2: var(--color-primary-dark);
  --el-color-success: var(--color-success);
  --el-color-warning: var(--color-warning);
  --el-color-danger: var(--color-error);
  --el-color-error: var(--color-error);
  --el-text-color-primary: var(--color-text);
  --el-text-color-regular: var(--color-text);
  --el-text-color-secondary: var(--color-text-muted);
  --el-text-color-placeholder: var(--color-text-disabled);
  --el-border-color: var(--color-border);
  --el-border-color-light: var(--color-border-light);
  --el-border-color-lighter: #e0d6bf;
  --el-bg-color: var(--color-surface);
  --el-bg-color-page: var(--color-bg);
  --el-bg-color-overlay: var(--color-surface);
  --el-fill-color-light: var(--color-surface-2);
  --el-fill-color-blank: var(--color-surface);
  --el-border-radius-base: 12px;
  --el-border-radius-small: 8px;
  --el-border-radius-round: 50px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: 'Nunito', 'Noto Sans SC', 'Zen Maru Gothic',
               -apple-system, BlinkMacSystemFont, 'PingFang SC',
               'Helvetica Neue', sans-serif;
  font-weight: 500;
  letter-spacing: 0.01em;
  background: var(--color-bg);
  /* 三层叠加背景：
     1. 暖米底色（var(--color-bg)）已设
     2. 浅色动森图案（叶子 / 贝壳 / 星 / 圆点）大面积平铺
     3. 极淡棕色颗粒点提供"纸张"质感 */
  background-image:
    url('./assets/decor/pattern.svg'),
    radial-gradient(circle, rgba(114, 93, 66, 0.06) 1.2px, transparent 1.4px),
    radial-gradient(circle, rgba(114, 93, 66, 0.04) 1px, transparent 1.2px);
  background-size: 240px 240px, 24px 24px, 36px 36px;
  background-position: 0 0, 0 0, 12px 12px;
  background-repeat: repeat, repeat, repeat;
  background-attachment: fixed, scroll, scroll;
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
}

/* 全局 emoji wobble：hover 摇头小动画，给所有 .nav-icon / .brand-icon /
   .home-avatar / .tile-emoji 等装饰元素增加可爱感。降级到 prefers-reduced-motion */
@keyframes animal-wobble {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-8deg); }
  75% { transform: rotate(8deg); }
}
.nav-icon,
.brand-icon,
.tile-emoji,
.chip-label::before {
  display: inline-block;
  transform-origin: center;
}
.nav-item:hover .nav-icon,
.phone-tile:hover .tile-emoji {
  animation: animal-wobble 0.6s ease;
}
@media (prefers-reduced-motion: reduce) {
  .nav-item:hover .nav-icon,
  .phone-tile:hover .tile-emoji {
    animation: none;
  }
}

/* ===== 路由切换动画：fade + 轻微下移 + 弹性曲线 =====
   离场 200ms 较快不打断用户；进场 320ms 拉慢一点带回弹感 */
.page-enter-active {
  animation: page-enter 0.32s cubic-bezier(0.25, 1.2, 0.4, 1);
}
.page-leave-active {
  animation: page-leave 0.18s ease-out;
}
@keyframes page-enter {
  0% { opacity: 0; transform: translateY(14px) scale(0.985); }
  100% { opacity: 1; transform: none; }
}
@keyframes page-leave {
  0% { opacity: 1; }
  100% { opacity: 0; transform: translateY(-6px); }
}

/* 容器级错峰弹入：给 .animal-pop 标记的元素分配 --i 序号 */
@keyframes animal-pop-in {
  0% { opacity: 0; transform: translateY(12px) scale(0.94); }
  60% { transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: none; }
}
.animal-pop {
  animation: animal-pop-in 0.42s cubic-bezier(0.25, 1.2, 0.4, 1) both;
  animation-delay: calc(var(--i, 0) * 60ms);
}
@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active,
  .animal-pop { animation: none !important; }
}

/* 页面标题底部装饰：薄荷青虚线 / 小波浪条
   .page-title 在多个 view 已存在；通过 ::after 加 12px 高的小波浪 */
.page-title {
  position: relative;
  display: inline-block;
  padding-bottom: 8px;
}
.page-title::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 8px;
  background:
    radial-gradient(circle at 50% 0%, transparent 0 3.5px, var(--color-primary) 3.5px 5px, transparent 5px),
    radial-gradient(circle at 50% 0%, transparent 0 2.5px, var(--color-primary-light) 2.5px 4px, transparent 4px);
  background-size: 14px 8px, 14px 8px;
  background-position: 0 0, 7px 0;
  background-repeat: repeat-x;
  opacity: 0.85;
}

/* ===== 全局 Element Plus 覆盖 ===== */
.el-card {
  border-radius: var(--radius-card) !important;
  border: 1px solid var(--color-border) !important;
  box-shadow: var(--shadow-card) !important;
  background: var(--color-surface) !important;
}
.el-card__header {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border) !important;
  padding: 14px 18px !important;
}
.el-card__body {
  padding: 18px !important;
}
.el-button--primary {
  background: var(--color-primary) !important;
  border-color: var(--color-primary) !important;
}
.el-button--primary:hover,
.el-button--primary:focus {
  background: var(--color-primary-dark) !important;
  border-color: var(--color-primary-dark) !important;
}
.el-tabs__item.is-active { color: var(--color-primary) !important; }
.el-tabs__active-bar { background: var(--color-primary) !important; }
.el-tabs__item:hover { color: var(--color-primary) !important; }

/* el-main */
.el-main {
  /* 不能再用实色，否则会盖住 body 的动森装饰图案 */
  background: transparent;
  padding: 20px;
  overflow-y: auto;
  overflow-x: hidden;
}
.el-main.has-topbar {
  padding-top: calc(var(--topbar-height) + 12px);
}

/* ===== 侧边栏（蓝色调浅色） ===== */
.app-aside {
  background: var(--color-primary-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 2px 0 8px rgba(37,99,235,0.08);
}
.drawer-inner {
  height: 100%;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 18px 14px;
  margin-bottom: 4px;
}
.brand-link { cursor: pointer; }
.brand-link:hover .brand-tree { transform: rotate(-6deg) scale(1.06); }
.brand-icon { font-size: 22px; }
.brand-tree {
  height: 40px;
  width: auto;
  filter: drop-shadow(0 2px 2px rgba(0,0,0,0.1));
  flex-shrink: 0;
}
.brand-name {
  font-size: 16px;
  font-weight: 800;
  color: var(--color-text-strong);
  letter-spacing: 0.05em;
}

.side-nav {
  flex: 0 0 auto;
  padding: 12px 14px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

/* 中间装饰区。overflow:hidden 兜底——无论贴士多长都不允许压到下方
   footer 的用户名/按钮区;正常情况由行数钳制 + 高度媒体查询保证不触发裁切 */
.side-mid {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: stretch;
  padding: 12px 12px 0;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}
.side-tip {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 0 2px;
}
.side-tip-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--color-surface);
  box-shadow: 0 3px 0 0 var(--shadow-anchor);
  flex-shrink: 0;
  cursor: pointer;
  animation: animal-tip-bob 4s ease-in-out infinite;
  transition: transform 0.2s ease;
}
.side-tip-avatar:hover {
  transform: scale(1.1);
}
.side-tip-avatar:active,
.side-tip-avatar.is-loading {
  /* 点击或正在请求时强烈摇头 0.5s 表示"在想"，loading 时持续 */
  animation: animal-tip-shake 0.5s ease;
}
.side-tip-avatar.is-loading {
  animation-iteration-count: infinite;
}
@keyframes animal-tip-bob {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-3px) rotate(-3deg); }
}
@keyframes animal-tip-shake {
  0%, 100% { transform: rotate(0deg); }
  20% { transform: rotate(-15deg) scale(1.1); }
  40% { transform: rotate(12deg) scale(1.1); }
  60% { transform: rotate(-10deg) scale(1.05); }
  80% { transform: rotate(8deg) scale(1.05); }
}
.side-tip-bubble {
  flex: 1;
  position: relative;
  background: var(--color-surface);
  border: 2px solid var(--color-border-light);
  border-radius: 14px 14px 14px 4px;
  padding: 8px 10px;
  font-size: 11px;
  color: var(--color-text);
  line-height: 1.5;
  min-width: 0;
  box-shadow: 0 2px 0 0 var(--shadow-anchor-light);
}
.side-tip-bubble::before {
  /* 气泡左下小尖角，指向头像 */
  content: "";
  position: absolute;
  left: -8px;
  bottom: 2px;
  width: 8px;
  height: 8px;
  background: var(--color-surface);
  border-left: 2px solid var(--color-border-light);
  border-bottom: 2px solid var(--color-border-light);
  transform: rotate(45deg);
  border-bottom-left-radius: 3px;
}
.side-tip-text {
  word-break: break-word;
  /* 最多 3 行,再长省略——LLM 偶尔话痨,不能让气泡无限长高 */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.side-clock {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  background: linear-gradient(135deg, var(--color-primary-light), var(--color-surface));
  border-radius: 16px;
  border: 2px solid var(--color-border-light);
  box-shadow: 0 3px 0 0 var(--shadow-anchor-light);
}
.clock-time {
  font-size: 22px;
  font-weight: 900;
  color: var(--color-primary-dark);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
}
.clock-date {
  font-size: 11px;
  color: var(--color-text-muted);
  font-weight: 600;
}

/* ── 竖向空间分级收纳(PC 侧边栏) ──
   brand+nav+footer 固定内容实测 ≈720px,贴士(3 行钳制)≈85px、时钟 ≈80px。
   矮视口按优先级让路:先缩海浪 → 收时钟 → 收贴士 → 整栏可滚动。
   阈值都留了 ~20px 余量,保证贴士永远不会和 footer 的用户名挤在一起 */
@media (max-height: 940px) {
  .side-wave { height: 34px; background-size: 150px 34px; margin-top: 10px; }
  .side-mid { gap: 8px; }
}
@media (max-height: 890px) {
  .side-clock { display: none; }
}
/* 紧凑模式:优先压缩品牌/导航/按钮的留白来保贴士(Anon 的小发言是招牌,
   能不砍就不砍),同时贴士降到 2 行 */
@media (max-height: 840px) {
  .brand { padding: 10px 18px 8px; margin-bottom: 0; }
  .side-nav { gap: 4px; padding: 8px 14px 4px; }
  .nav-item { padding: 7px 12px; }
  .side-footer { padding-top: 8px; }
  .side-actions { gap: 4px; }
  .user-info { margin-bottom: 8px; }
  .side-tip-text { -webkit-line-clamp: 2; }
}
@media (max-height: 750px) {
  /* 紧凑完仍放不下(<750px 的桌面视口不多见):收贴士 + 整栏可滚动兜底。
     注意 :not(.drawer-inner) 隔离——手机抽屉的高度阈值单独管理(见下),
     不能被 PC 的规则连带误杀(真机浏览器视口普遍 650-750px) */
  .app-aside:not(.drawer-inner) .side-tip { display: none; }
  .app-aside:not(.drawer-inner) { overflow-y: auto; }
}

/* ── 移动端抽屉:时钟是纯装饰(手机自带时钟),直接不放;贴士钳到 2 行。
   抽屉固定内容 ≈600px,贴士到 ~660px 视口都放得下——真机浏览器扣掉
   地址栏一般还有 650-750px,正常都能看到贴士;只有横屏才收 ── */
.drawer-inner .side-clock { display: none; }
.drawer-inner .side-tip-text { -webkit-line-clamp: 2; }
.drawer-inner .side-wave { height: 32px; background-size: 150px 32px; margin-top: 10px; }
@media (max-height: 620px) {
  .drawer-inner .side-tip { display: none; }
  .drawer-inner { overflow-y: auto; }
}
.nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--color-primary);
  color: var(--color-primary);
  background: #fff;
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
  box-shadow: none;
}
.nav-item:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
}
.nav-item.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(37,99,235,0.25);
  font-weight: 700;
}
.nav-icon { font-size: 15px; }
.nav-avatar {
  width: 28px;
  height: 28px;
  vertical-align: middle;
  flex-shrink: 0;
  background: #fff;
  border-radius: 50%;
  padding: 1px;
  box-shadow: 0 2px 0 0 var(--shadow-anchor-light);
  transition: transform 0.2s ease;
}
.nav-item.active .nav-avatar {
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 0 0 rgba(0,0,0,0.15);
}
.nav-item:hover .nav-avatar {
  transform: scale(1.1) rotate(-5deg);
}

.side-footer {
  padding: 14px 10px 0;
  margin-top: 4px;
  position: relative;
}
/* 海浪条带：sidebar 底部，宽度撑满，重复平铺 */
.side-wave {
  margin: 16px -18px 0;
  height: 60px;
  background: url('@/assets/decor/wave.svg') repeat-x bottom / 180px 60px;
  pointer-events: none;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-name {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
}
.side-btn {
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--color-primary);
  background: #fff;
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.side-btn:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
}
.side-btn.primary {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
  box-shadow: 0 3px 0 0 var(--shadow-anchor, #bdaea0);
}
.side-btn.primary:hover {
  background: var(--color-primary-dark);
  color: #fff;
  transform: translateY(-1px);
  box-shadow: 0 4px 0 0 var(--shadow-anchor, #bdaea0);
}
.side-btn.primary:active {
  transform: translateY(2px);
  box-shadow: 0 1px 0 0 var(--shadow-anchor, #bdaea0);
}
.side-btn.danger {
  border-color: #ef4444;
  color: #ef4444;
  background: #fff;
}
.side-btn.danger:hover {
  background: #fee2e2;
  color: #dc2626;
  border-color: #dc2626;
}

/* ===== 移动端顶栏（浅色） ===== */
.mobile-topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--topbar-height);
  background: var(--color-bg);
  display: flex;
  align-items: center;
  padding: 0 12px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(37,99,235,0.10);
}
.topbar-menu-btn {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  line-height: 1;
}
.topbar-menu-btn:hover {
  background: var(--color-bg);
  color: var(--color-primary);
}
.topbar-title {
  flex: 1;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 600;
  text-align: center;
}
.topbar-decide-btn {
  width: 36px;
  height: 36px;
  margin-right: 6px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: 50%;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 0 0 var(--shadow-anchor, #bdaea0);
  transition: transform 0.15s, box-shadow 0.15s;
}
.topbar-decide-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 0 0 var(--shadow-anchor, #bdaea0);
}
.topbar-decide-btn:active {
  transform: translateY(2px);
  box-shadow: 0 1px 0 0 var(--shadow-anchor, #bdaea0);
}
.topbar-decide-btn.checkup {
  background: var(--color-warning, #f5c31c);
}

.topbar-user {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 移动端抽屉内边距清零 */
.mobile-drawer .el-drawer__body {
  padding: 0 !important;
  overflow: hidden;
}

/* LLM 配置弹窗 provider 选择下方说明 */
.provider-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 4px;
  line-height: 1.5;
}
</style>
