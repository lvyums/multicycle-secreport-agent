<template>
  <div class="preview-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>报告预览</span>
          <div class="actions">
            <el-select v-if="siblings.length > 1" v-model="compareTarget" placeholder="版本对比" size="small" style="width: 180px" clearable @change="doCompare">
              <el-option v-for="s in siblings" :key="s.id" :label="`v${s.versionNo} · ${s.windowStart.slice(0, 10)}`" :value="s.id" />
            </el-select>
            <el-button size="small" @click="goBack">返回</el-button>
            <el-button size="small" type="primary" @click="refresh">刷新</el-button>
          </div>
        </div>
      </template>

      <template v-if="version">
        <el-descriptions :column="4" border size="small" class="meta">
          <el-descriptions-item label="标题" :span="2">{{ version.title }}</el-descriptions-item>
          <el-descriptions-item label="周期">
            <el-tag size="small">{{ CYCLE_LABELS[version.cycle] || version.cycle }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusType(version.status)">{{ VERSION_STATUS_LABELS[version.status] || version.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="窗口">{{ version.windowStart }} ~ {{ version.windowEnd }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ version.createdAt }}</el-descriptions-item>
          <el-descriptions-item label="操作者">{{ version.operator }}</el-descriptions-item>
        </el-descriptions>

        <div class="op-bar">
          <!-- 审核流转 -->
          <template v-if="version.status === 'DRAFT'">
            <el-button size="small" type="warning" @click="audit('submit')">提交审核</el-button>
          </template>
          <template v-else-if="version.status === 'REVIEWING'">
            <el-button size="small" type="success" @click="audit('approve')">审核通过</el-button>
            <el-button size="small" type="danger" @click="audit('reject')">驳回</el-button>
          </template>
          <template v-else-if="version.status === 'APPROVED'">
            <el-button size="small" @click="audit('archive')">归档</el-button>
          </template>
          <!-- 推送 -->
          <el-select v-model="pushChannel" size="small" style="width: 130px; margin-left: 12px">
            <el-option v-for="c in channels" :key="c" :label="channelLabel(c)" :value="c" />
          </el-select>
          <el-button size="small" type="primary" :disabled="version.status !== 'APPROVED'" @click="doPush">
            推送{{ version.status !== 'APPROVED' ? '(需终审)' : '' }}
          </el-button>
        </div>
      </template>

      <div v-if="loading" v-loading="true" class="loading-wrap" />
      <template v-else-if="content">
        <div class="md-body" v-html="renderedHtml" />

        <!-- 版本对比结果 -->
        <el-card v-if="compareResult" shadow="never" class="compare-card">
          <template #header>
            <div class="toolbar">
              <span>版本对比: v{{ compareResult.base.versionNo || compareResult.base.id }} → v{{ compareResult.target.versionNo || compareResult.target.id }}</span>
              <el-button size="small" link @click="compareResult = null">关闭</el-button>
            </div>
          </template>
          <el-table :data="compareResult.metricDiff" size="small" max-height="320">
            <el-table-column prop="label" label="指标" width="130" />
            <el-table-column label="基准" width="100">
              <template #default="{ row }">{{ fmtNum(row.base) }}</template>
            </el-table-column>
            <el-table-column label="对比" width="100">
              <template #default="{ row }">{{ fmtNum(row.target) }}</template>
            </el-table-column>
            <el-table-column label="变化" width="140">
              <template #default="{ row }">
                <span :class="row.delta > 0 ? 'up' : row.delta < 0 ? 'down' : ''">
                  {{ row.delta > 0 ? '+' : '' }}{{ fmtNum(row.delta) }}<template v-if="row.pct !== null"> ({{ row.pct > 0 ? '+' : '' }}{{ row.pct }}%)</template>
                </span>
              </template>
            </el-table-column>
          </el-table>
          <el-alert v-if="compareResult.textDiff.sections.length" type="info" :closable="false" class="mt8">
            <template #title>
              文本变化: 增 {{ compareResult.textDiff.totalAdded }} 行 / 删 {{ compareResult.textDiff.totalRemoved }} 行 / 改 {{ compareResult.textDiff.totalChanged }} 行
            </template>
            <ul class="diff-list">
              <li v-for="(s, i) in compareResult.textDiff.sections.slice(0, 6)" :key="i">
                <b>[{{ s.section }}]</b> +{{ s.added }} -{{ s.removed }} ~{{ s.changed }}
                <span v-for="(sm, j) in s.samples" :key="j" class="diff-sample" :class="sm[0] === '+' ? 'add' : sm[0] === '-' ? 'del' : 'mod'">
                  {{ sm[0] }} {{ sm[1] }}
                </span>
              </li>
            </ul>
          </el-alert>
        </el-card>
      </template>
      <el-empty v-else description="请从历史报告列表进入预览" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS, VERSION_STATUS_LABELS } from '@/types'
import type { ReportVersion } from '@/types'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const content = ref('')
const version = ref<ReportVersion | null>(null)
const siblings = ref<ReportVersion[]>([])
const channels = ref<string[]>(['local'])
const pushChannel = ref('local')
const compareTarget = ref<number | null>(null)
const compareResult = ref<any>(null)

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function statusType(s: string) {
  return { DRAFT: 'warning', APPROVED: 'success', ARCHIVED: 'info', FAILED: 'danger', REVIEWING: 'primary' }[s] || 'info'
}

function channelLabel(c: string) {
  return { local: '本地归档', dingtalk: '钉钉', wecom: '企微', email: '邮件' }[c] || c
}

function fmtNum(n: number) {
  return typeof n === 'number' ? (Math.abs(n) >= 100 ? Math.round(n) : n) : n
}

/** 极简 Markdown 渲染（标题/列表/表格/粗体） */
const renderedHtml = computed(() => {
  if (!content.value) return ''
  const lines = content.value.split('\n')
  const html: string[] = []
  let inTable = false
  for (const line of lines) {
    const t = line.trim()
    if (t.startsWith('|') && t.endsWith('|')) {
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
  const [r, d] = await Promise.all([
    Api.version.content(versionId),
    Api.version.detail(versionId),
  ])
  notifyError(r)
  notifyError(d)
  if (r.success) content.value = (r.data as any)?.content || ''
  if (d.success) {
    version.value = (d.data as any) as ReportVersion
    loadSiblings(version.value)
  }
  loading.value = false
}

async function loadSiblings(v: ReportVersion) {
  const r = await Api.version.list({ cycle: v.cycle, limit: 50 })
  if (r.success) {
    siblings.value = ((r.data as any)?.items || []).filter((s: ReportVersion) => s.id !== v.id)
  }
  const c = await Api.publish.channels()
  if (c.success) channels.value = (c.data as any)?.channels || ['local']
}

async function audit(action: string) {
  const label = { submit: '提交审核', approve: '审核通过', reject: '驳回', archive: '归档' }[action]
  try {
    await ElMessageBox.confirm(`确认${label}该版本？`, '审核操作', { type: 'warning' })
  } catch {
    return
  }
  const r = await Api.version.audit(action, version.value!.id, { operator: 'webuser' })
  notifyError(r)
  if (r.success) {
    ElMessage.success(`已${label}: ${(r.data as any)?.statusLabel}`)
    load()
  }
}

async function doPush() {
  const r = await Api.publish.push({ versionId: version.value!.id, channel: pushChannel.value })
  notifyError(r)
  if (r.success) ElMessage.success('推送成功')
}

async function doCompare(targetId: number) {
  if (!targetId || !version.value) return
  const r = await Api.version.compare(version.value.id, targetId)
  notifyError(r)
  if (r.success) compareResult.value = r.data
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
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.meta {
  margin-bottom: 10px;
}
.op-bar {
  margin-bottom: 12px;
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
.compare-card {
  margin-top: 18px;
}
.mt8 {
  margin-top: 8px;
}
.diff-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
}
.diff-sample {
  display: inline-block;
  margin: 0 8px 2px 0;
  padding: 0 6px;
  border-radius: 3px;
  font-family: monospace;
}
.add {
  background: #f0f9eb;
  color: #67c23a;
}
.del {
  background: #fef0f0;
  color: #f56c6c;
}
.mod {
  background: #fdf6ec;
  color: #e6a23c;
}
.up {
  color: #f56c6c;
  font-weight: 600;
}
.down {
  color: #67c23a;
  font-weight: 600;
}
</style>
