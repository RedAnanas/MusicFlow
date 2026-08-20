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
    layout="total, sizes, prev, pager, next, jumper"
    @current-change="emit('update:currentPage', $event)"
    @size-change="handleSizeChange"
  />
</template>

<style scoped>
.table-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
