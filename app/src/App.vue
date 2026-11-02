<script setup>
import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue';
import ApiConnection from './components/ApiConnection.vue';
import VerificationWorkspace from './components/VerificationWorkspace.vue';
import EnvironmentDoctor from './components/EnvironmentDoctor.vue';
import BookLibrary from './components/BookLibrary.vue';
import ConfigEditor from './components/ConfigEditor.vue';
import JobsPage from './components/JobsPage.vue';
import OverviewDashboard from './components/OverviewDashboard.vue';
const verificationMode = __VERIFICATION_MODE__;

const pages = {
  overview: { title: 'Tổng quan', icon: '▦', subtitle: 'Kết nối các bước sản xuất audiobook của bạn.', heading: 'Không gian làm việc đã sẵn sàng', description: 'Giao diện và API được khởi động riêng; trạng thái kết nối thực tế hiển thị phía trên. Quản lý truyện sẽ có sau các task dữ liệu và import.', note: 'Chưa có số liệu truyện để hiển thị.' },
  library: { title: 'Thư viện truyện', icon: '▤', subtitle: 'Một nơi cho nội dung, giọng đọc và tiến độ từng bộ truyện.', heading: 'Thư viện sẽ được kết nối ở T05–T10', description: 'Tạo bộ truyện, nhập TXT và quản lý chương sẽ có sau các task dữ liệu. Hiện chưa truy cập hoặc thay đổi thư mục input/output của bạn.', note: 'Chưa có dữ liệu thư viện được kết nối.' },
  jobs: { title: 'Công việc', icon: '☷', subtitle: 'Theo dõi tiến độ và kết quả các tác vụ chạy nền.', heading: 'Hàng đợi sẽ được kết nối ở T15', description: 'Tạo tác vụ, xem tiến độ, dừng và chạy tiếp sẽ được triển khai theo backlog. Không có job nền nào được khởi động từ trang này.', note: 'Worker chưa triển khai.' },
  settings: { title: 'Cấu hình', icon: '☷', subtitle: 'Thiết lập mặc định và cấu hình riêng cho từng bộ truyện.', heading: 'Cấu hình sẽ được kết nối ở T11–T12', description: 'Provider, giọng đọc, batch và glossary chưa được đưa vào form. Các cấu hình hiện tại của công cụ CLI vẫn được giữ nguyên.', note: 'Chưa đọc API key hoặc cấu hình model.' },
  environment: { title: 'Môi trường', icon: '⌁', subtitle: 'Kiểm tra các thành phần cần thiết trước khi sản xuất audio.', heading: 'Kiểm tra môi trường', description: 'Kiểm tra điều kiện cục bộ trước khi tạo audio.', note: 'Không nạp model hoặc gọi mạng.' },
};
if (verificationMode) pages.verification = { title: 'Kiểm thử offline', icon: '◇', subtitle: 'Workspace mẫu tách biệt, không gọi dịch vụ thật.' };
const hash = ref(location.hash.slice(1) || 'overview');
const routeParts = computed(() => hash.value.split('?')[0].split('/'));
const routeQuery = computed(() => new URLSearchParams(hash.value.split('?')[1] || ''));
const activePage = computed(() => Object.hasOwn(pages, routeParts.value[0]) ? routeParts.value[0] : 'overview');
const page = computed(() => pages[activePage.value]);
const navigation = computed(() => Object.entries(pages).map(([key, value]) => ({ key, ...value })));
const focusMain = () => document.getElementById('main').focus();
const syncHash = () => { hash.value = location.hash.slice(1) || 'overview'; };
onMounted(() => window.addEventListener('hashchange', syncHash));
onUnmounted(() => window.removeEventListener('hashchange', syncHash));
watchEffect(() => { document.title = `${page.value.title} · novel2voice`; });
</script>

<template>
  <a class="absolute -top-24 left-3 z-10 rounded-lg bg-surface p-3 text-brand focus:top-3" href="#main" @click.prevent="focusMain">Đến nội dung chính</a>
  <header class="flex h-16 items-center justify-between border-b border-line bg-surface px-[18px] sm:h-[72px] sm:px-7">
    <a class="flex items-center gap-3 text-xl font-semibold tracking-[-.6px]" href="#overview">
      <span class="grid size-[35px] place-items-center rounded-[10px] bg-brand text-[30px] leading-none text-brand-ink" aria-hidden="true">≋</span>
      <span>novel2voice</span><span class="rounded bg-canvas px-2 py-1 text-[10px] font-medium tracking-widest text-muted">STUDIO</span>
    </a>
    <span class="hidden items-center gap-2 text-xs text-muted sm:flex"><span class="size-1.5 rounded-full bg-success"></span>Máy cá nhân</span>
  </header>
  <div class="grid min-h-[calc(100vh-64px)] grid-cols-1 sm:min-h-[calc(100vh-72px)] sm:grid-cols-[180px_minmax(0,1fr)] lg:grid-cols-[220px_minmax(0,1fr)]">
    <aside class="flex flex-col border-b border-line bg-surface p-2 sm:border-r sm:border-b-0 sm:px-3.5 sm:py-[30px]">
      <p class="mx-3.5 mb-3 hidden text-[10px] tracking-[1.6px] text-muted sm:block">WORKSPACE</p>
      <nav class="flex flex-wrap gap-1 sm:block" aria-label="Điều hướng chính">
        <template v-for="item in navigation" :key="item.key">
          <p v-if="item.key === 'settings'" class="mx-3.5 mt-[34px] mb-3 hidden text-[10px] tracking-[1.6px] text-muted sm:block">THIẾT LẬP</p>
          <a :href="`#${item.key}`" :data-page="item.key" :aria-current="activePage === item.key ? 'page' : undefined"
            class="mb-0 flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs sm:mb-1 sm:gap-3 sm:px-3.5 sm:py-3 sm:text-[13px]"
            :class="activePage === item.key ? 'bg-soft font-medium text-brand' : 'text-muted hover:bg-canvas'">
            <span class="w-[15px] text-center text-[15px] sm:w-[18px] sm:text-lg" aria-hidden="true">{{ item.icon }}</span>{{ item.title }}
          </a>
        </template>
      </nav>
      <div class="mt-auto hidden px-3.5 pt-9 text-[11px] text-muted sm:block">
        <span class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-success"></span>Local workspace</span>
        <p class="mt-2.5">v1.0 · Đang hoàn thiện v1.1</p>
      </div>
    </aside>
    <main id="main" tabindex="-1" class="mx-auto w-full min-w-0 max-w-[1260px] px-4 py-6 sm:p-6 lg:p-9">
      <div class="mb-[22px] flex flex-wrap items-start justify-between gap-2.5 sm:mb-8 sm:gap-4">
        <div><p class="mb-2 text-[10px] tracking-[1.7px] text-muted">KHÔNG GIAN LÀM VIỆC</p><h1 id="page-title" class="mb-2 text-[25px] font-semibold tracking-[-.8px] sm:text-[28px]">{{ page.title }}</h1><p id="page-subtitle" class="text-[13px] text-muted">{{ page.subtitle }}</p></div>
        <span class="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[11px] whitespace-nowrap text-muted sm:mt-2">{{ verificationMode ? 'T02 · Kiểm thử offline' : 'v1.1 · Nền tảng web' }}</span>
      </div>
      <div v-if="verificationMode" id="verification-banner" class="mb-5 rounded-xl border border-brand bg-soft p-4 text-brand" role="note"><strong class="text-sm">CHẾ ĐỘ KIỂM THỬ</strong><p class="mt-1 text-xs">Dữ liệu mẫu, âm thử và bản dịch giả lập. Không gọi AI/TTS thật. <a class="underline" href="#verification">Mở workspace nghiệm thu →</a></p></div>
      <ApiConnection />
      <VerificationWorkspace v-if="activePage === 'verification'" />
      <BookLibrary v-else-if="activePage === 'library'" :book-id="routeParts[1] || ''" :chapter-id="routeParts[2] || ''" />
      <JobsPage v-else-if="activePage === 'jobs'" :job-id="routeParts[1] || ''" :initial-book-id="routeQuery.get('book') || ''" :initial-status="routeQuery.get('status') || ''" />
      <ConfigEditor v-else-if="activePage === 'settings'" />
      <EnvironmentDoctor v-else-if="activePage === 'environment'" />
      <OverviewDashboard v-else-if="activePage === 'overview'" :resource="routeParts[1] || ''" :book-id="routeQuery.get('book') || ''" />
      <section v-else id="page-content" class="mt-6 flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-[18px] py-[30px] text-center sm:px-[30px] sm:py-11" aria-labelledby="content-title">
        <span class="grid size-[52px] place-items-center rounded-[14px] bg-canvas text-[25px] text-muted" aria-hidden="true">▤</span>
        <h2 id="content-title" class="mt-1 text-base font-semibold">{{ page.heading }}</h2>
        <p class="max-w-[520px] text-[13px] leading-[1.8] text-muted">{{ page.description }}</p>
        <div class="mt-2 rounded-md bg-canvas px-3.5 py-2.5 text-[11px] text-muted">{{ page.note }}</div>
      </section>
      <footer class="mt-6 flex flex-col flex-wrap justify-between gap-1 text-[11px] text-muted sm:flex-row sm:gap-4">Dữ liệu nằm trên máy của bạn <span>Thư viện lưu cục bộ · Không nạp model khi mở trang</span></footer>
    </main>
  </div>
</template>
