<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>报告选配</span>
          <el-button type="primary" size="small" :loading="saving" @click="onSave">保存配置</el-button>
        </div>
      </template>

      <el-form label-width="120px" v-loading="loading">
        <el-form-item label="启用周期">
          <el-checkbox-group v-model="form.enabledCycles">
            <el-checkbox v-for="c in allCycles" :key="c.value" :value="c.value">{{ c.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-divider content-position="left">报告章节</el-divider>
        <el-form-item label="章节开关">
          <div class="section-grid">
            <el-checkbox v-for="s in sectionsMeta" :key="s.key" v-model="form.sections[s.key]">
              {{ s.label }}
            </el-checkbox>
          </div>
          <div class="hint">关闭的章节在生成的报告中整段移除（如不需要漏洞章节可关闭）</div>
        </el-form-item>

        <el-divider content-position="left">推送与自动化</el-divider>
        <el-form-item label="推送渠道">
          <el-checkbox-group v-model="form.pushChannels">
            <el-checkbox v-for="c in channels" :key="c" :value="c">{{ channelLabel(c) }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="生成后自动推送">
          <el-switch v-model="autoGenerate" active-text="开启" inactive-text="关闭" />
          <div class="hint">开启后，每次报告生成成功自动推送到所选渠道</div>
        </el-form-item>
        <el-form-item label="EMPTY 推送策略">
          <el-select v-model="emptyPushMode" style="width: 280px">
            <el-option label="不推送（默认，仅生成占位报告）" value="skip" />
            <el-option label="不推送 + 告警通知" value="alert_only" />
            <el-option label="正常推送（占位报告也推送）" value="push" />
          </el-select>
          <div class="hint">EMPTY=窗口内无告警/漏洞数据。建议开启「不推送 + 告警通知」，
            避免把「数据源故障导致的空数据」当成「真的没有安全事件」推给领导</div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Api } from '@/api'

const loading = ref(false)
const saving = ref(false)
const form = ref<any>({ enabledCycles: [], sections: {}, pushChannels: [] })
const autoGenerate = ref(false)
const emptyPushMode = ref('skip')

const allCycles = [
  { value: 'DAILY', label: '日报' },
  { value: 'WEEKLY', label: '周报' },
  { value: 'MONTHLY', label: '月报' },
  { value: 'QUARTERLY', label: '季报' },
  { value: 'YEARLY', label: '年报' },
]
const sectionsMeta = [
  { key: 'overview', label: '总体态势' },
  { key: 'alert', label: '告警分析' },
  { key: 'vuln', label: '漏洞情况' },
  { key: 'attack', label: '攻击行为' },
  { key: 'trend', label: '趋势预测' },
  { key: 'suggestion', label: '安全建议' },
]
const channels = ['local', 'dingtalk', 'wecom', 'email']
const channelLabel = (c: string) =>
  ({ local: '本地归档', dingtalk: '钉钉', wecom: '企微', email: '邮件' }[c] || c)

async function load() {
  loading.value = true
  try {
    const r = await Api.config.reportGet()
    const d = r.data
    form.value = {
      enabledCycles: d.enabledCycles || [],
      sections: { ...(d.sections || {}) },
      pushChannels: d.pushChannels || [],
    }
    autoGenerate.value = d.autoGenerate === 'enabled'
    emptyPushMode.value = d.emptyPushMode || 'skip'
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await Api.config.reportSave({
      enabledCycles: form.value.enabledCycles,
      sections: form.value.sections,
      pushChannels: form.value.pushChannels,
      autoGenerate: autoGenerate.value ? 'enabled' : 'disabled',
      emptyPushMode: emptyPushMode.value,
    })
    ElMessage.success('配置已保存')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.section-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
}
.hint {
  width: 100%;
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
