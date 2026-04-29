<template>
  <div class="report-body">
    <section>
      <h2>项目概述</h2>
      <p>{{ report.overview }}</p>
      <p v-if="report.llm_note" class="note">{{ report.llm_note }}</p>
    </section>

    <section>
      <h2>技术栈</h2>
      <div class="chips">
        <span v-for="item in report.tech_stack" :key="item.name" class="chip">
          {{ item.name }} <small>{{ item.reason }}</small>
        </span>
      </div>
    </section>

    <details class="report-collapse">
      <summary>
        <span>目录结构</span>
        <small>点击展开完整目录树</small>
      </summary>
      <p class="section-hint">整个模块默认折叠；展开后，内部目录还可以继续逐级展开。</p>
      <DirectoryTree :nodes="directoryTree" />
    </details>

    <section>
      <h2>核心模块</h2>
      <div class="module-groups">
        <article v-for="group in moduleGroups" :key="group.role" class="module-group">
          <h3>{{ group.role }}</h3>
          <div class="module-list">
            <div v-for="module in group.items" :key="module.path" class="module-row">
              <strong>{{ module.path }}</strong>
              <span>{{ module.summary || '这个文件更像辅助配置，建议结合调用方阅读。' }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section>
      <h2>数据流</h2>
      <ol>
        <li v-for="step in report.data_flow" :key="step">{{ step }}</li>
      </ol>
    </section>

    <section>
      <h2>设计模式</h2>
      <ul>
        <li v-for="pattern in report.design_patterns" :key="pattern">{{ pattern }}</li>
      </ul>
    </section>

    <section>
      <h2>阅读建议</h2>
      <ul>
        <li v-for="guide in report.reading_guide" :key="guide">{{ guide }}</li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DirectoryTree from './DirectoryTree.vue'

const props = defineProps({
  report: {
    type: Object,
    required: true
  }
})

const directoryTree = computed(() => {
  const root = []
  const byPath = new Map()

  for (const item of props.report.directory_structure || []) {
    const parts = item.path.split('/').filter(Boolean)
    let siblings = root
    let currentPath = ''

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part
      let node = byPath.get(currentPath)
      if (!node) {
        node = {
          name: part,
          path: currentPath,
          type: index === parts.length - 1 ? item.type : 'dir',
          children: []
        }
        byPath.set(currentPath, node)
        siblings.push(node)
      }
      siblings = node.children
    })
  }

  return sortNodes(root)
})

const moduleGroups = computed(() => {
  const groups = new Map()
  for (const module of props.report.core_modules || []) {
    const role = module.role || '其他文件'
    if (!groups.has(role)) groups.set(role, [])
    groups.get(role).push(module)
  }
  return Array.from(groups, ([role, items]) => ({ role, items }))
})

function sortNodes(nodes) {
  return nodes
    .map((node) => ({ ...node, children: sortNodes(node.children) }))
    .sort((a, b) => {
      if (a.children.length && !b.children.length) return -1
      if (!a.children.length && b.children.length) return 1
      return a.name.localeCompare(b.name)
    })
}
</script>
