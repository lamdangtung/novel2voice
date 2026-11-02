import { computed, onMounted, onUnmounted, ref } from 'vue';
import { getHealth } from '../lib/api-client.js';

export function useApiHealth(apiOrigin) {
  const status = ref('loading');
  const description = ref('Đang kiểm tra máy chủ local…');
  const version = ref('Chưa xác định');
  const lastCheck = ref('Chưa kiểm tra');
  const checking = ref(false);
  let controller, timer;
  const components=ref(null);
  let mounted = true;
  const statusLabel = computed(() => ({ loading: 'Đang kết nối', connected: 'Đã kết nối', error: 'Mất kết nối' })[status.value]);
  const help = computed(() => status.value === 'error'
    ? 'Kiểm tra terminal đang chạy ứng dụng. Bật lại API rồi bấm Thử lại.'
    : components.value ? `Database: ${components.value.database==='ready'?'sẵn sàng':'khởi tạo khi mở thư viện'} · Worker: ${components.value.worker==='ready'?'đang hoạt động':'chưa phản hồi; kiểm tra terminal launcher'}.` : 'Đang kiểm tra các thành phần local.');

  async function checkConnection() {
    if (checking.value) return;
    checking.value = true;
    status.value = 'loading';
    description.value = 'Đang kiểm tra máy chủ local…';
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const health = await getHealth(apiOrigin, { signal: controller.signal });
      if (!mounted) return;
      status.value = 'connected';
      description.value = 'API local đang phản hồi bình thường.';
      version.value = health.version;components.value=health.components;
    } catch (error) {
      if (!mounted) return;
      status.value = 'error';
      description.value = error.name === 'AbortError' ? 'API chưa phản hồi trong 4 giây.' : error.message;
      version.value = 'Chưa xác định';
    } finally {
      clearTimeout(timeout);
      if (mounted) {
        lastCheck.value = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
        checking.value = false;
      }
    }
  }
  const checkWhenVisible = () => { if (!document.hidden) checkConnection(); };
  onMounted(() => {
    window.addEventListener('focus', checkConnection);
    document.addEventListener('visibilitychange', checkWhenVisible);
    checkConnection();timer=setInterval(checkWhenVisible,10000);
  });
  onUnmounted(() => {
    mounted = false;clearInterval(timer);
    controller?.abort();
    window.removeEventListener('focus', checkConnection);
    document.removeEventListener('visibilitychange', checkWhenVisible);
  });
  return { status, statusLabel, description, version, lastCheck, checking, help, checkConnection };
}
