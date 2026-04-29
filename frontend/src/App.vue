<template>
  <main class="shell">
    <section class="hero panel">
      <div>
        <p class="eyebrow">Project Helper</p>
        <h1>把陌生开源项目讲到傻子也能懂</h1>
        <p class="subtitle">
          输入 GitHub 仓库，自动克隆、分析技术栈、核心模块、数据流和阅读路线，并支持带源码工具的 AI 问答。
        </p>
      </div>
      <form class="search-card" @submit.prevent="analyze">
        <label for="repo">GitHub 仓库地址</label>
        <div class="input-row">
          <input id="repo" v-model="repoUrl" placeholder="https://github.com/tiangolo/fastapi" />
          <button :disabled="loading">{{ loading ? '分析中...' : '开始分析' }}</button>
        </div>
        <label for="model">模型选择</label>
        <select id="model" v-model="selectedModel">
          <option v-for="model in modelOptions" :key="model.value" :value="model.value">
            {{ model.label }}
          </option>
        </select>
        <label class="force">
          <input v-model="force" type="checkbox" />
          强制重新分析，忽略缓存
        </label>
        <p v-if="error" class="error">{{ error }}</p>
      </form>
    </section>

    <section class="grid">
      <aside class="panel history">
        <div class="section-title">
          <span>历史项目</span>
          <button class="ghost" @click="loadProjects">刷新</button>
        </div>
        <button
          v-for="item in projects"
          :key="item.id"
          class="project-item"
          :class="{ active: item.id === projectId }"
          @click="openProject(item.id)"
        >
          <strong>{{ item.repo_name }}</strong>
          <span>{{ item.status }}</span>
        </button>
        <p v-if="!projects.length" class="muted">还没有分析记录。</p>
      </aside>

      <section class="panel progress-panel">
        <div class="section-title">
          <span>实时进度</span>
          <strong>{{ progress }}%</strong>
        </div>
        <div class="progress-bar"><span :style="{ width: `${progress}%` }"></span></div>
        <ol class="timeline">
          <li v-for="(event, index) in events" :key="index">
            <span>{{ event.percent || 0 }}%</span>
            <p>{{ event.message }}</p>
          </li>
        </ol>
      </section>
    </section>

    <section v-if="completeNotice" class="notice success">
      <strong>分析完成</strong>
      <span>{{ completeNotice }}</span>
    </section>

    <section v-if="report" class="report-grid">
      <article class="panel report" v-highlight>
        <div class="section-title">
          <span>完整分析报告</span>
          <small>{{ currentProject?.repo_url }} · {{ report.model || selectedModel }}</small>
        </div>
        <ReportView :report="report" />
      </article>

      <aside class="panel chat">
        <div class="section-title">
          <span>源码问答 Agent</span>
          <small>流式输出</small>
        </div>
        <div class="chat-log">
          <div v-for="(message, index) in messages" :key="index" :class="['bubble', message.role]">
            {{ message.content }}
          </div>
        </div>
        <form class="chat-form" @submit.prevent="ask">
          <textarea v-model="question" placeholder="比如：这个项目启动流程是什么？核心接口在哪里？"></textarea>
          <button :disabled="chatting || !question.trim()">{{ chatting ? '回答中...' : '提问' }}</button>
        </form>
      </aside>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getProject, listProjects, startAnalysis, streamChat, subscribeAnalysis } from './api'
import ReportView from './components/ReportView.vue'

const repoUrl = ref('')
const force = ref(false)
const loading = ref(false)
const chatting = ref(false)
const error = ref('')
const projectId = ref('')
const projects = ref([])
const events = ref([])
const currentProject = ref(null)
const report = ref(null)
const question = ref('')
const messages = ref([])
const completeNotice = ref('')
const selectedModel = ref('deepseek-v4-flash')
const modelOptions = [
  { label: 'DeepSeek V4 Flash（默认，非思考）', value: 'deepseek-v4-flash' },
  { label: 'DeepSeek V4 Pro（思考模式）', value: 'deepseek-v4-pro' },
  { label: 'DeepSeek Chat（兼容旧名称）', value: 'deepseek-chat' },
  { label: 'DeepSeek Reasoner（兼容旧名称）', value: 'deepseek-reasoner' }
]
let unsubscribe = null

const progress = computed(() => events.value.at(-1)?.percent || (report.value ? 100 : 0))

onMounted(loadProjects)

async function analyze() {
  error.value = ''
  loading.value = true
  events.value = []
  report.value = null
  messages.value = []
  completeNotice.value = ''
  try {
    const result = await startAnalysis(repoUrl.value, force.value, selectedModel.value)
    projectId.value = result.project_id
    if (result.cached) {
      await openProject(result.project_id)
      events.value.push({ message: '命中缓存，直接展示历史报告', percent: 100 })
      completeNotice.value = '命中缓存，报告已加载，可以开始源码问答。'
      return
    }
    subscribe(result.project_id)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function subscribe(id) {
  if (unsubscribe) unsubscribe()
  unsubscribe = subscribeAnalysis(id, async (type, event) => {
    events.value.push(event)
    if (type === 'completed') {
      report.value = event.payload.report
      currentProject.value = await getProject(id)
      completeNotice.value = '报告已生成，可以从下方报告开始阅读，或在右侧向 Agent 提问。'
      await loadProjects()
      if (unsubscribe) unsubscribe()
    }
    if (type === 'failed') {
      error.value = event.message
      completeNotice.value = ''
      if (unsubscribe) unsubscribe()
    }
  })
}

async function openProject(id) {
  projectId.value = id
  const item = await getProject(id)
  currentProject.value = item
  report.value = item.report
  repoUrl.value = item.repo_url
  events.value = [{ message: item.status === 'completed' ? '已加载缓存报告' : `当前状态：${item.status}`, percent: item.status === 'completed' ? 100 : 0 }]
  completeNotice.value = item.status === 'completed' ? '已加载历史报告，可以继续阅读或提问。' : ''
}

async function loadProjects() {
  projects.value = await listProjects()
}

async function ask() {
  const text = question.value.trim()
  if (!text || !projectId.value) return
  messages.value.push({ role: 'user', content: text })
  const assistant = { role: 'assistant', content: '' }
  messages.value.push(assistant)
  question.value = ''
  chatting.value = true
  try {
    await streamChat(projectId.value, text, selectedModel.value, (token) => {
      assistant.content += token
    })
  } catch (err) {
    assistant.content += `\n请求失败：${err.message}`
  } finally {
    chatting.value = false
  }
}
</script>
