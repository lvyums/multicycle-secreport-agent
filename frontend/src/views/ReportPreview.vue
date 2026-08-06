<template>
  <div class="preview-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>报告预览</span>
          <div>
            <el-button size="small" @click="goBack">返回</el-button>
            <el-button size="small" type="primary" @click="refresh">刷新</el-button>
          </div>
        </div>
      </template>

      <div v-if="loading" v-loading="true" class="loading-wrap" />
      <div v-else-if="content" class="md-body" v-html="renderedHtml" />
      <el-empty v-else description="请从历史报告列表进入预览" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Api } from '@/api'
import { notifyError } from '@/api/request'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const content = ref('')

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 极简 Markdown 渲染（标题/列表/表格/粗体），V1.1 够用 */
const renderedHtml = computed(() => {
  if (!content.value) return ''
  const lines = content.value.split('\n')
  const html: string[] = []
  let inTable = false
  for (const line of lines) {
    const t = line.trim()
    if (t.startsWith('|') && t.endsWith('|')) {
      // 分隔行（|---|）跳过不渲染
      if (/^\|[\s\-:|]+\|$/.test(t)) {
        if (!inTable) {
          html.push('<table class="md-table">')
          inTable = true
        }
        continue
      }
      if (!inTable) {
        html.push('<table class="md-table">')
        inTable = true
      }
      const cells = t.split('|').filter((_, i, arr) => i > 0 && i < arr.length - 1)
      const isHeader = !inTable || html[html.length - 1]?.includes('<table')
      html.push(
        '<tr>' + cells.map((c) => `<${isHeader ? 'th' : 'td'}>${escapeHtml(c.trim())}</${isHeader ? 'th' : 'td'}>`).join('') + '</tr>',
      )
      continue
    }
    if (inTable) {
      html.push('</table>')
      inTable = false
    }
    if (/^#{1,4}\s/.test(t)) {
      const level = t.match(/^#+/)?.[0].length || 1
      html.push(`<h${Math.min(level, 4)}>${escapeHtml(t.replace(/^#+\s*/, ''))}</h${Math.min(level, 4)}>`)
    } else if (t.startsWith('- ') || t.startsWith('* ')) {
      html.push(`<li>${escapeHtml(t.replace(/^[-*]\s*/, ''))}</li>`)
    } else if (t === '') {
      html.push('<div class="md-blank"></div>')
    } else {
      html.push(`<p>${escapeHtml(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</p>`)
    }
  }
  if (inTable) html.push('</table>')
  return html.join('\n')
})

async function load() {
  const versionId = Number(route.params.versionId)
  if (!versionId) return
  loading.value = true
  const r = await Api.version.content(versionId)
  notifyError(r)
  if (r.success) {
    content.value = (r.data as any)?.content || ''
  }
  loading.value = false
}

function refresh() {
  load()
}
function goBack() {
  router.push('/reports')
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.loading-wrap {
  min-height: 200px;
}
.md-body {
  line-height: 1.8;
  font-size: 14px;
}
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3) {
  margin: 18px 0 10px;
}
.md-body :deep(p) {
  margin: 8px 0;
}
.md-body :deep(.md-table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
}
.md-body :deep(.md-table th), .md-body :deep(.md-table td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  font-size: 13px;
}
.md-body :deep(.md-table th) {
  background: #f5f7fa;
}
</style>
