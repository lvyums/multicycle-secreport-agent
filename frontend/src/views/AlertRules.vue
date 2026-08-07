<template>
  <div class="alert-page">
    <el-card shadow="never">
      <template #header>
        <div class="page-header">
          <span>告警规则（阈值 DB 热读，保存后下一轮检查生效，无需重启）</span>
          <el-button type="primary" size="small" @click="load">刷新</el-button>
        </div>
      </template>
      <el-table :data="rules" v-loading="loading" stripe>
        <el-table-column prop="name" label="规则" min-width="140" />
        <el-table-column prop="ruleKey" label="标识" min-width="150" />
        <el-table-column label="判定" min-width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.threshold" :min="0" :max="100000" :step="row.ruleKey === 'llm_fallback_rate' ? 0.1 : 1" size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="windowHours" label="窗口" width="100">
          <template #default="{ row }">近 {{ row.windowHours }}h</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" active-value="enabled" inactive-value="disabled"
                       active-text="启用" inactive-text="停用" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" size="small" :disabled="!dirty(row)" @click="save(row)">保存</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无告警规则</template>
      </el-table>
      <div class="tip">
        💡 告警触发后写入审计日志（ALERT_xxx）并推送钉钉/企微（推送模式由系统配置决定），
        同规则 30 分钟内不重复触发。
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Api } from '../api'

interface AlertRule {
  id: number
  ruleKey: string
  name: string
  threshold: number
  windowHours: number
  enabled: string
  updatedAt?: string
  updatedBy?: string
}

const rules = ref<AlertRule[]>([])
const loading = ref(false)
const originals = new Map<number, string>()

function dirty(row: AlertRule): boolean {
  const orig = originals.get(row.id)
  return orig !== `${row.threshold}|${row.enabled}`
}

async function load() {
  loading.value = true
  const res = await Api.alert.rules()
  loading.value = false
  if (res.success && res.data) {
    rules.value = (res.data as { items: AlertRule[] }).items
    originals.clear()
    rules.value.forEach(r => originals.set(r.id, `${r.threshold}|${r.enabled}`))
  }
}

async function save(row: AlertRule) {
  const res = await Api.alert.updateRule(row.id, { threshold: row.threshold, enabled: row.enabled })
  if (res.success) {
    originals.set(row.id, `${row.threshold}|${row.enabled}`)
    ElMessage.success('已保存，下一轮检查生效')
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.tip {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
}
</style>
