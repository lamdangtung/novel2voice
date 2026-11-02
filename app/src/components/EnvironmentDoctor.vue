<script setup>
import { ref, watch } from 'vue';
const verificationMode = __VERIFICATION_MODE__;
const provider = ref('vieneu');
const scenario = ref('real');
const report = ref(null);
const pending = ref(false);
const error = ref('');
const labels = { ready: 'Đạt', missing: 'Thiếu', invalid: 'Cần sửa', unverified: 'Chưa xác minh', optional: 'Tùy chọn' };
watch([provider, scenario], () => { report.value = null; error.value = ''; });
watch(provider, value => { if (!['piper', 'vieneu'].includes(value) && scenario.value === 'missing_model') scenario.value = 'real'; });
async function run() {
  pending.value = true; error.value = ''; report.value = null;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${__API_ORIGIN__}/api/v1/environment/doctor`, {
      method: 'POST', credentials: 'omit', cache: 'no-store', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-Novel2Voice-Client': 'web' },
      body: JSON.stringify({ provider: provider.value, scenario: scenario.value }),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error?.message || 'Không kiểm tra được môi trường.');
    report.value = value;
  } catch (e) {
    error.value = e.name === 'AbortError' ? 'Kiểm tra quá thời gian. Thử lại hoặc kiểm tra launcher.' : 'Không kiểm tra được môi trường. Kiểm tra kết nối API rồi thử lại.';
  } finally { clearTimeout(timeout); pending.value = false; }
}
</script>
<template>
  <section class="mt-6 rounded-xl border border-line bg-surface p-5 sm:p-7" aria-labelledby="doctor-title">
    <h2 id="doctor-title" class="text-base font-semibold">Kiểm tra trước khi tạo audio</h2>
    <p class="mt-2 text-sm leading-6 text-muted">Kiểm tra FFmpeg, thư viện và cấu hình trong môi trường CLI/TTS. Không nạp model, tải file hoặc gọi dịch vụ bên ngoài.</p>
    <form class="mt-5 flex flex-wrap items-end gap-4" @submit.prevent="run">
      <label class="grid gap-2 text-sm" for="doctor-provider">Provider
        <select id="doctor-provider" v-model="provider" :disabled="pending" class="rounded-lg border border-line bg-canvas px-3 py-2.5">
          <option value="vieneu">VieNeu</option><option value="piper">Piper</option><option value="edge-tts">Edge TTS</option><option value="openai">OpenAI TTS</option>
        </select>
      </label>
      <label v-if="verificationMode" class="grid gap-2 text-sm" for="doctor-scenario">Tình huống nghiệm thu
        <select id="doctor-scenario" v-model="scenario" :disabled="pending" class="rounded-lg border border-line bg-canvas px-3 py-2.5">
          <option value="real">Môi trường thật</option><option value="missing_dependency">Giả lập thiếu thư viện</option>
          <option v-if="['piper','vieneu'].includes(provider)" value="missing_model">Giả lập thiếu model</option>
        </select>
      </label>
      <button id="run-doctor" :disabled="pending" class="rounded-lg border border-brand bg-brand px-5 py-2.5 text-sm font-medium text-brand-ink disabled:opacity-50">{{ pending ? 'Đang kiểm tra…' : 'Kiểm tra môi trường' }}</button>
    </form>
    <p v-if="error" id="doctor-error" role="alert" class="mt-5 rounded-lg border border-line p-4 text-sm">{{ error }}</p>
    <p v-if="!report && !pending && !error" class="mt-6 text-sm text-muted">Chọn provider rồi kiểm tra để xem kết quả thực tế.</p>
    <div v-if="report" class="mt-6" aria-live="polite">
      <div id="doctor-summary" class="rounded-lg border border-line bg-canvas p-4">
        <p class="font-semibold">{{ report.status === 'blocked' ? 'Cần xử lý trước khi tạo audio' : 'Các điều kiện cục bộ đã đạt' }}</p>
        <p class="mt-2 text-xs leading-5 text-muted">{{ report.notice }}</p>
        <p class="mt-2 text-xs text-muted">Python được kiểm tra: .venv ở gốc project · Cấu hình: biến môi trường server ưu tiên hơn .env.</p>
        <p v-if="report.fixture" id="doctor-fixture" class="mt-3 font-semibold text-brand">KẾT QUẢ CÓ GIẢ LẬP — {{ report.fixture }}</p>
      </div>
      <ul class="mt-4 divide-y divide-line">
        <li v-for="check in report.checks" :key="check.id" :data-check="check.id" :data-status="check.status" class="py-4">
          <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-medium break-all">{{ check.label }}</h3><span class="rounded-md px-2 py-1 text-xs" :class="check.status === 'ready' ? 'bg-soft text-brand' : 'bg-canvas text-muted'">{{ labels[check.status] }}</span></div>
          <p class="mt-2 text-sm leading-6 text-muted">{{ check.message }}</p>
          <p v-if="check.remedy" class="mt-1 text-xs leading-5">Cách xử lý: {{ check.remedy }}</p>
        </li>
      </ul>
      <p class="mt-4 text-xs leading-5 text-muted">Sửa .env rồi kiểm tra lại để đọc cấu hình mới. Nếu thay biến môi trường hoặc PATH của tiến trình, hãy khởi động lại launcher. Thử giọng thật sẽ được triển khai ở task riêng.</p>
    </div>
  </section>
</template>
