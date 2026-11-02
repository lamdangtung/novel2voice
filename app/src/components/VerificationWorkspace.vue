<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { verificationRequest, reportUrl, sampleUrl } from '../lib/verification-client.js';

const name = ref('demo');
const workspaces = ref([]);
const busy = ref(false);
const message = ref('');
const error = ref('');
const failProvider = ref('none');
const failOnCall = ref(2);
const faultMode = ref('call');
const failChapter = ref('A/2');
const delayMs = ref(0);
const confirmation = ref('');
const rootPath = ref('');
const current = computed(() => workspaces.value.find(item => item.name === name.value));
const report = computed(() => current.value?.latest_report);
const validName = computed(() => /^[a-z][a-z0-9-]{0,31}$/.test(name.value) && !['input', 'output', 'models'].includes(name.value));
const buttonClass = 'rounded-lg border border-line px-3.5 py-2.5 text-xs font-medium hover:border-brand disabled:cursor-not-allowed disabled:opacity-50';
const fieldClass = 'w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink';
watch(failProvider, value => {
  failOnCall.value = value === 'translator' ? 1 : 2;
  failChapter.value = value === 'translator' ? 'A/en/1' : 'A/2';
});
watch(name, () => { confirmation.value = ''; error.value = ''; message.value = ''; });

async function action(label, operation) {
  busy.value = true; error.value = ''; message.value = label;
  try { await operation(); }
  catch (failure) { error.value = failure.message; message.value = ''; }
  finally { busy.value = false; }
}
function mergeWorkspace(item) {
  workspaces.value = [...workspaces.value.filter(existing => existing.name !== item.name), item].sort((a, b) => a.name.localeCompare(b.name));
}
async function refresh() {
  await action('Đang đọc workspace…', async () => {
    const value = await verificationRequest();
    workspaces.value = value.workspaces; rootPath.value = value.root; message.value = '';
  });
}
async function create() {
  await action('Đang tạo dữ liệu mẫu…', async () => {
    mergeWorkspace(await verificationRequest('', { name: name.value }));
    message.value = 'Workspace đã sẵn sàng. Dữ liệu tồn tại trước đó được giữ nguyên.';
  });
}
async function run() {
  await action('Đang chạy self-check offline…', async () => {
    const result = await verificationRequest(`/${name.value}/self-check`, {
      fail_provider: failProvider.value,
      fail_on_call: Number(failOnCall.value),
      fail_chapter: failProvider.value !== 'none' && faultMode.value === 'chapter' ? failChapter.value : '',
      delay_ms: Number(delayMs.value),
    });
    mergeWorkspace({ ...current.value, latest_report: result });
    message.value = result.status === 'passed' ? 'Self-check hoàn thành. Audio thử và bản dịch giả lập đã được lưu.' : 'Self-check có lỗi chủ động. Xem báo cáo và nhật ký bên dưới.';
  });
}
async function reset() {
  await action('Đang reset workspace kiểm thử…', async () => {
    mergeWorkspace(await verificationRequest(`/${name.value}/reset`, { confirmation: confirmation.value }));
    confirmation.value = ''; message.value = 'Đã khôi phục fixture ban đầu; kết quả và nhật ký cũ trong workspace này đã xóa.';
  });
}
onMounted(refresh);
</script>

<template>
  <div class="mt-6 space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-line bg-surface p-5">
      <div class="min-w-0 flex-1"><h2 class="text-base font-semibold">Workspace nghiệm thu lặp lại</h2><p class="mt-1 text-xs leading-6 text-muted">Tạo → self-check → reset → chạy lại. Hai bộ truyện mẫu và các ca lỗi nằm riêng khỏi kho truyện thật.</p><p v-if="rootPath" class="mt-2 break-all font-mono text-[11px] text-muted">{{ rootPath }}</p></div>
      <button :class="buttonClass" :disabled="busy" @click="refresh">Tải lại danh sách</button>
    </div>
    <p v-if="error" class="rounded-lg bg-danger-soft p-4 text-sm text-danger" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-lg bg-soft p-4 text-xs text-brand" role="status" aria-live="polite">{{ message }}</p>
    <section class="rounded-xl border border-line bg-surface p-5" aria-labelledby="workspace-title">
      <h2 id="workspace-title" class="text-base font-semibold">1. Chọn hoặc tạo workspace</h2>
      <div class="mt-4 flex flex-wrap items-end gap-3">
        <label class="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted">Tên workspace<input id="workspace-name" v-model.trim="name" :class="fieldClass" maxlength="32" placeholder="demo" :disabled="busy" /></label>
        <button id="create-workspace" :class="buttonClass" class="bg-brand text-brand-ink hover:opacity-90" :disabled="busy || !validName" @click="create">Tạo dữ liệu mẫu</button>
      </div>
      <p class="mt-2 text-[11px] text-muted">Chữ thường, số và dấu gạch nối. Không nhận đường dẫn input/output hoặc thư mục tùy ý.</p>
      <div v-if="workspaces.length" class="mt-3 flex flex-wrap items-center gap-2"><span class="text-xs text-muted">Đã có:</span><button v-for="item in workspaces" :key="item.name" :class="buttonClass" :disabled="busy" @click="name = item.name">{{ item.name }}</button></div>
      <div v-if="current" class="mt-4 space-y-2 rounded-lg bg-canvas p-4 text-xs"><p><strong>{{ current.manifest.books.length }} bộ truyện mẫu</strong> · {{ current.manifest.files.length }} file fixture · {{ current.manifest.fixture_version }}</p><p class="break-all font-mono text-[11px] text-muted">{{ current.path }}</p><p class="text-muted">Có chương 1/2/10, thư mục con, EN/VI, file rỗng, encoding lỗi, trùng số, nội dung đã sửa và audio hỏng/mơ hồ.</p></div>
      <p v-else class="mt-4 text-xs text-muted">Workspace này chưa có dữ liệu. Tạo dữ liệu mẫu trước khi chạy self-check.</p>
    </section>
    <section class="rounded-xl border border-line bg-surface p-5" aria-labelledby="self-check-title">
      <h2 id="self-check-title" class="text-base font-semibold">2. Self-check và lỗi chủ động</h2>
      <p class="mt-1 text-xs leading-6 text-muted">Luồng chuẩn: 3 lần tạo âm thử + 1 lần dịch giả lập. Audio là tiếng tone 440 Hz, không phải giọng đọc.</p>
      <div class="mt-4 grid gap-4 sm:grid-cols-2">
        <label class="flex flex-col gap-2 text-xs text-muted">Gây lỗi ở<select id="fault-provider" v-model="failProvider" :class="fieldClass" :disabled="busy"><option value="none">Không gây lỗi</option><option value="tts">TTS giả lập</option><option value="translator">Translator giả lập</option></select></label>
        <label class="flex flex-col gap-2 text-xs text-muted">Độ trễ mỗi lần gọi (ms)<input id="delay-ms" v-model.number="delayMs" type="number" min="0" max="1000" :class="fieldClass" :disabled="busy" /></label>
        <template v-if="failProvider !== 'none'">
          <label class="flex flex-col gap-2 text-xs text-muted">Chọn vị trí lỗi<select v-model="faultMode" :class="fieldClass" :disabled="busy"><option value="call">Theo lần gọi / đoạn</option><option value="chapter">Theo chương</option></select></label>
          <label v-if="faultMode === 'call'" class="flex flex-col gap-2 text-xs text-muted">Lần gọi gây lỗi<input id="fault-call" v-model.number="failOnCall" type="number" min="1" :max="failProvider === 'translator' ? 1 : 3" :class="fieldClass" :disabled="busy" /></label>
          <label v-else class="flex flex-col gap-2 text-xs text-muted">Chương gây lỗi<select v-model="failChapter" :class="fieldClass" :disabled="busy"><template v-if="failProvider === 'tts'"><option>A/1</option><option>A/2</option></template><option>A/en/1</option></select></label>
        </template>
      </div>
      <button id="run-self-check" :class="buttonClass" class="mt-4 bg-brand text-brand-ink hover:opacity-90" :disabled="busy || !current" @click="run">{{ busy ? 'Đang xử lý…' : 'Chạy self-check offline' }}</button>
    </section>
    <section v-if="report" id="verification-report" class="space-y-4 rounded-xl border border-line bg-surface p-5" aria-labelledby="report-title">
      <div class="flex flex-wrap items-center justify-between gap-3"><div><h2 id="report-title" class="text-base font-semibold">3. Kết quả {{ report.run_id }}</h2><p class="mt-1 text-xs text-muted">{{ report.tts_calls }} lần gọi TTS · {{ report.translator_calls }} lần gọi translator</p></div><span id="check-status" class="rounded-md px-3 py-1.5 text-xs" :class="report.status === 'passed' ? 'bg-success-soft text-success' : 'bg-danger-soft text-danger'">{{ report.status === 'passed' ? 'Đạt' : 'Có lỗi' }}</span></div>
      <p class="text-xs text-muted">{{ report.notice }}</p>
      <ul v-if="report.errors.length" class="space-y-2 text-xs text-danger"><li v-for="item in report.errors" :key="item.chapter_id">{{ item.message }}</li></ul>
      <div class="grid gap-3 sm:grid-cols-2"><div v-for="audio in report.outputs" :key="audio.file" class="min-w-0 rounded-lg bg-canvas p-3"><p class="mb-2 text-xs font-medium">{{ audio.chapter_id }} · {{ audio.valid ? 'Audio hợp lệ' : 'Audio lỗi' }} · {{ audio.duration_seconds?.toFixed(2) }}s</p><audio controls preload="none" class="h-9 w-full" :src="sampleUrl(name, report.run_id, audio.file)"></audio></div></div>
      <pre v-if="report.translation" class="overflow-auto rounded-lg bg-canvas p-4 text-xs leading-6 whitespace-pre-wrap">{{ report.translation }}</pre>
      <div class="overflow-x-auto"><table class="w-full text-left text-xs"><thead class="border-b border-line text-muted"><tr><th class="p-2">Provider</th><th class="p-2">Lần gọi</th><th class="p-2">Chương / Đoạn</th><th class="p-2">Trạng thái</th></tr></thead><tbody><tr v-for="(call, index) in report.calls" :key="index" class="border-b border-line"><td class="p-2">{{ call.provider }}</td><td class="p-2">{{ call.call }}</td><td class="p-2">{{ call.chapter_id }} / {{ call.chunk_index }}</td><td class="p-2">{{ call.status }}</td></tr></tbody></table></div>
      <a id="download-report" :href="reportUrl(name, report.run_id)" :class="buttonClass" class="inline-block" download>Tải báo cáo JSON</a>
    </section>
    <section v-if="current" class="rounded-xl border border-line bg-surface p-5" aria-labelledby="reset-title"><h2 id="reset-title" class="text-base font-semibold">Reset riêng workspace {{ name }}</h2><p class="mt-1 text-xs leading-6 text-muted">Xóa kết quả/nhật ký của workspace này, khôi phục bộ fixture ban đầu. Không ảnh hưởng workspace khác hoặc kho truyện thật.</p><label class="mt-4 flex flex-col gap-2 text-xs text-muted">Nhập RESET {{ name }} để xác nhận<input id="reset-confirmation" v-model="confirmation" :class="fieldClass" :disabled="busy" /></label><button id="reset-workspace" :class="buttonClass" class="mt-3 text-danger" :disabled="busy || confirmation !== `RESET ${name}`" @click="reset">Reset dữ liệu kiểm thử</button></section>
  </div>
</template>
