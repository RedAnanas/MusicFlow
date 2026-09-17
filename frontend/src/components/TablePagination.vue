<script setup lang="ts">
withDefaults(defineProps<{
  currentPage: number
  pageSize: number
  total: number
  pageSizes?: number[]
}>(), {
  pageSizes: () => [20, 50, 100],
})

const emit = defineEmits<{
  (event: 'update:currentPage', value: number): void
  (event: 'update:pageSize', value: number): void
  (event: 'size-change', value: number): void
}>()

const handleSizeChange = (pageSize: number) => {
  emit('update:pageSize', pageSize)
  emit('update:currentPage', 1)
  emit('size-change', pageSize)
}
</script>

<template>
  <el-pagination
    class="table-pagination"
    :current-page="currentPage"
    :page-size="pageSize"
    :page-sizes="pageSizes"
    :total="total"
    layout="sizes, prev, pager, next, jumper"
    @current-change="emit('update:currentPage', $event)"
    @size-change="handleSizeChange"
  />
</template>

<style scoped>
.table-pagination {
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 4px 0;
  margin-top: 14px;
  border-top: 1px solid #edf0f4;
}
@media (max-width: 700px) { .table-pagination { justify-content: space-between; gap: 6px; padding: 14px 0 18px; margin-top: 12px; }.table-pagination :deep(.el-pagination__sizes), .table-pagination :deep(.el-pagination__jump) { margin: 0; }.table-pagination :deep(.el-pagination__jump) { display: flex; align-items: center; gap: 4px; }.table-pagination :deep(.el-pagination__goto), .table-pagination :deep(.el-pagination__classifier) { display: none; }.table-pagination :deep(.el-pagination__sizes) { margin-right: auto; }.table-pagination :deep(.el-pagination__pager) { flex: 0 0 auto; }.table-pagination :deep(.btn-prev), .table-pagination :deep(.btn-next) { min-width: 26px; margin: 0; } }
</style>
