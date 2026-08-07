<template>
  <div class="forbidden-page">
    <el-result icon="warning" title="403 无权限访问" sub-title="当前角色无权访问该页面，如需开通请联系管理员">
      <template #extra>
        <el-button type="primary" @click="$router.push('/dashboard')">返回任务看板</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.forbidden-page {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}
</style>
