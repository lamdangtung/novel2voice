<script setup>
import { ref, watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
import TxtImport from './TxtImport.vue';
import ConfigEditor from './ConfigEditor.vue';
import GlossaryEditor from './GlossaryEditor.vue';
import AudioImport from './AudioImport.vue';
import VoiceSampler from './VoiceSampler.vue';
const props = defineProps({ chapterId: {type:String,default:''}, bookId: { type: String, default: '' } });
const languages=ref([]);
const languageLabel=code=>languages.value.find(item=>item.code===code)?.label||code;
const books = ref([]), total = ref(0), offset = ref(0), current = ref(null);
const name = ref(''), language = ref('vi'), pending = ref(false), error = ref(''), message = ref('');
const requestId = ref(crypto.randomUUID());
const contentRevision = ref(0);
async function load() {
  pending.value = true; error.value = ''; message.value = ''; current.value = null;
  try {
    languages.value=(await libraryRequest('/workspace/languages')).items;
    if (props.bookId) {
      current.value = await libraryRequest(`/${encodeURIComponent(props.bookId)}`);
      name.value = current.value.name; language.value = current.value.language;
    } else {
      const data = await libraryRequest(`?offset=${offset.value}&limit=20`);
      books.value = data.items; total.value = data.total; name.value = ''; language.value = 'vi';
    }
  } catch (e) { error.value = e.message; }
  finally { pending.value = false; }
}
watch(() => props.bookId, () => { offset.value = 0; load(); }, { immediate: true });
async function save() {
  if (!name.value.trim()) { error.value = 'Nhập tên bộ truyện.'; return; }
  pending.value = true; error.value = ''; message.value = '';
  try {
    if (current.value) {
      current.value = await libraryRequest(`/${current.value.id}`, { name: name.value.trim(), language: language.value, revision: current.value.revision }, 'PATCH');
      name.value = current.value.name; message.value = 'Đã lưu thay đổi.';
    } else {
      const book = await libraryRequest('', { name: name.value.trim(), language: language.value, request_id: requestId.value });
      requestId.value = crypto.randomUUID(); offset.value = 0;
      await load(); message.value = `Đã tạo “${book.name}”.`;
    }
  } catch (e) { error.value = e.message; }
  finally { pending.value = false; }
}
function page(delta) { offset.value += delta; load(); }
</script>
<template>
  <section class="mt-6 space-y-5" aria-labelledby="library-title">
    <a v-if="bookId" href="#library" class="text-sm text-brand">← Thư viện truyện</a>
    <div class="rounded-xl border border-line bg-surface p-5 sm:p-7">
      <h2 id="library-title" class="text-base font-semibold">{{ bookId ? (current?.name || 'Chi tiết bộ truyện') : 'Thư viện của bạn' }}</h2>
      <p class="mt-2 text-sm text-muted">{{ bookId ? 'Chọn ngôn ngữ gốc của truyện. Bản dịch và giọng đọc hiện hướng tới tiếng Việt.' : 'Tạo bộ truyện trước khi nhập nội dung chương.' }}</p>
      <p v-if="pending" class="mt-4 text-sm text-muted" role="status">Đang xử lý…</p>
      <div v-if="error" role="alert" id="library-error" class="mt-4 rounded-lg border border-line p-3 text-sm">{{ error }} <button type="button" :disabled="pending" class="ml-2 text-brand underline" @click="load">Tải lại</button></div>
      <p v-if="message" id="library-message" role="status" class="mt-4 text-sm text-brand">{{ message }}</p>
      <form v-if="!bookId || current" class="mt-5 flex flex-wrap items-end gap-4" @submit.prevent="save">
        <label class="grid w-full gap-2 text-sm sm:w-auto sm:min-w-72" for="book-name">Tên bộ truyện
          <input id="book-name" v-model="name" maxlength="200" required :disabled="pending" class="rounded-lg border border-line bg-canvas px-3 py-2.5" placeholder="Ví dụ: Hành trình phương Bắc" />
        </label>
        <label class="grid gap-2 text-sm" for="book-language">Ngôn ngữ gốc
          <select id="book-language" v-model="language" :disabled="pending" class="rounded-lg border border-line bg-canvas px-3 py-2.5"><option v-for="item in languages" :key="item.code" :value="item.code">{{item.label}}</option></select>
        </label>
        <button id="save-book" :disabled="pending" class="rounded-lg bg-brand px-5 py-2.5 text-sm font-medium text-brand-ink disabled:opacity-50">{{ current ? 'Lưu thay đổi' : 'Tạo bộ truyện' }}</button>
      </form>
      <p class="mt-3 text-xs leading-5 text-muted">Hỗ trợ 22 ngôn ngữ gốc; dịch/process hướng tới tiếng Việt. Đổi ngôn ngữ sẽ giữ file cũ, đánh dấu bản dịch/audio cần kiểm tra và yêu cầu xem lại kế hoạch.</p>
      <div v-if="current" id="book-details" class="mt-6 space-y-2 rounded-lg bg-canvas p-4 text-xs text-muted">
        <p class="break-all">ID: {{ current.id }}</p><p class="break-all">Vùng lưu riêng: {{ current.storage }}</p>
        <p>Phiên bản thông tin: {{ current.revision }}</p>
        <p>Nội dung chương được lưu riêng trong vùng quản lý của truyện.</p>
      </div>
    </div>
    <details v-if="current" class="rounded-xl border border-line bg-surface p-4"><summary class="cursor-pointer text-sm font-medium">Cấu hình riêng cho truyện</summary><ConfigEditor :book-id="current.id" /></details>
    <details v-if="current" class="rounded-xl border border-line bg-surface p-4"><summary class="cursor-pointer text-sm font-medium">Glossary của truyện</summary><GlossaryEditor :book-id="current.id" /></details>
    <details v-if="current" class="rounded-xl border border-line bg-surface p-4"><summary class="cursor-pointer text-sm font-medium">Nhập MP3 đã có</summary><AudioImport :book-id="current.id" @imported="contentRevision++" /></details>
    <details v-if="current" class="rounded-xl border border-line bg-surface p-4"><summary class="cursor-pointer text-sm font-medium">Giọng đọc và mẫu thử</summary><VoiceSampler :book-id="current.id" /></details>
    <TxtImport v-if="current" :key="current.id" :book-id="current.id" :external-refresh="contentRevision" :initial-chapter-id="chapterId" />
    <template v-if="!bookId">
      <div class="flex items-center justify-between gap-3 text-sm"><p>{{ total }} bộ truyện</p><button :disabled="pending" class="text-brand underline" @click="load">Làm mới</button></div>
      <p v-if="!pending && !error && total === 0" id="library-empty" class="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">Thư viện đang trống. Tạo bộ truyện đầu tiên bằng form phía trên.</p>
      <ul class="grid gap-4 md:grid-cols-2">
        <li v-for="book in books" :key="book.id" class="min-w-0 rounded-xl border border-line bg-surface p-5">
          <a :href="`#library/${book.id}`" class="book-link block text-base font-semibold text-brand break-words">{{ book.name }}</a>
          <p class="mt-2 text-xs text-muted">{{ languageLabel(book.language) }}</p>
          <p class="mt-3 text-xs text-muted">Mở để xem và chỉnh sửa →</p>
        </li>
      </ul>
      <div v-if="total > 20" class="flex items-center justify-between text-sm"><button :disabled="pending || offset === 0" @click="page(-20)">← Trước</button><span>{{ offset+1 }}–{{ Math.min(offset+20,total) }} / {{ total }}</span><button :disabled="pending || offset+20 >= total" @click="page(20)">Sau →</button></div>
    </template>
  </section>
</template>
