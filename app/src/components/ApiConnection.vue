<script setup>
import { computed } from 'vue';
import { useApiHealth } from '../composables/useApiHealth.js';

const apiOrigin = __API_ORIGIN__;
const { status, statusLabel, description, version, lastCheck, checking, help, checkConnection } = useApiHealth(apiOrigin);
const badgeStyle = computed(() => ({
  connected: 'bg-success-soft text-success',
  error: 'bg-danger-soft text-danger',
  loading: 'bg-soft text-brand',
})[status.value]);
</script>

<template>
  <section class="connection overflow-hidden rounded-xl border border-line bg-surface" aria-labelledby="connection-title" :data-state="status">
    <div class="flex flex-wrap items-center gap-3 px-4 py-5 sm:flex-nowrap sm:gap-3.5 sm:p-6">
      <div class="grid size-[42px] shrink-0 place-items-center rounded-[10px] bg-soft text-[27px] text-brand" aria-hidden="true">⌁</div>
      <div class="min-w-0 flex-1">
        <h2 id="connection-title" class="mb-1 text-base font-semibold">Kết nối API</h2>
        <p id="connection-description" class="text-[13px] text-muted">{{ description }}</p>
      </div>
      <span id="connection-status" class="ml-[54px] rounded-md px-2.5 py-1.5 text-xs whitespace-nowrap sm:ml-auto" :class="badgeStyle" role="status" aria-live="polite">{{ statusLabel }}</span>
    </div>
    <div class="grid grid-cols-2 gap-4 px-4 pb-5 sm:px-6 sm:pb-6 lg:grid-cols-[1.5fr_1fr_1fr]">
      <div class="col-span-2 flex min-w-0 flex-col gap-2 lg:col-span-1">
        <span class="text-[11px] text-muted">Máy chủ</span>
        <code id="api-url" class="text-xs break-all">{{ apiOrigin }}/api/v1</code>
      </div>
      <div class="flex flex-col gap-2"><span class="text-[11px] text-muted">Lần kiểm tra gần nhất</span><span id="last-check" class="text-[13px]">{{ lastCheck }}</span></div>
      <div class="flex flex-col gap-2"><span class="text-[11px] text-muted">Phiên bản API</span><span id="api-version" class="text-[13px]">{{ version }}</span></div>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-4 border-t border-line p-4 sm:flex-nowrap sm:px-6">
      <p id="connection-help" class="text-xs text-muted">{{ help }}</p>
      <button id="retry" type="button" class="min-h-10 shrink-0 rounded-lg border px-3.5 py-2 text-xs font-medium transition-colors disabled:cursor-wait disabled:opacity-60"
        :class="status === 'error' ? 'border-brand bg-brand text-brand-ink hover:opacity-90' : 'border-line bg-surface hover:bg-soft'"
        :disabled="checking" @click="checkConnection">
        {{ checking ? 'Đang kiểm tra…' : status === 'error' ? 'Thử lại' : 'Kiểm tra lại' }}
      </button>
    </div>
  </section>
</template>
