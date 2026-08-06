<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="main-aside">
      <div class="brand">
        <el-icon :size="22"><DataAnalysis /></el-icon>
        <span>多周期网安报告</span>
      </div>
      <el-menu :default-active="activeMenu" router class="main-menu">
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>任务看板</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <span>历史报告</span>
        </el-menu-item>
        <el-menu-item index="/schedule">
          <el-icon><Timer /></el-icon>
          <span>调度配置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="main-header">
        <div class="header-title">{{ pageTitle }}</div>
        <div class="header-right">
          <el-tag size="small" type="info">V0.1 框架底座</el-tag>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
const pageTitle = computed(() => (route.meta?.title as string) || '')
</script>

<style scoped>
.main-layout {
  height: 100%;
}
.main-aside {
  background: #1d2129;
  color: #fff;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  padding: 0 16px;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.main-menu {
  border-right: none;
  background: transparent;
}
.main-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.72);
}
.main-menu :deep(.el-menu-item.is-active) {
  color: #409eff;
  background: rgba(64, 158, 255, 0.12);
}
.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.main-content {
  background: #f5f7fa;
}
</style>
