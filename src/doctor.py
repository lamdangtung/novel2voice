"""Read-only preflight shared by CLI and web; never imports a TTS SDK."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = {'edge-tts': 'edge_tts', 'openai': 'openai', 'piper': 'piper', 'vieneu': 'vieneu'}
# Run in the actual CLI interpreter, not the API environment. Top-level find_spec
# only locates packages; it does not import them or initialise provider models.
PROBE = """import importlib.util,json,sys
names=json.loads(sys.argv[1])
print(json.dumps({n:importlib.util.find_spec(n) is not None for n in names}))
"""


def read_config(root=ROOT):
    from dotenv.main import DotEnv
    # Same precedence as CLI: process environment overrides root .env. Re-read
    # each check so editing .env can be verified without restarting the API.
    return {**DotEnv(root / '.env', override=False).dict(), **os.environ}


def inspect_runtime(python):
    try:
        result = subprocess.run([str(python), '-I', '-c', PROBE,
                                 json.dumps(['openai', 'edge_tts', 'piper', 'vieneu', 'dotenv', 'typer', 'rich', 'tqdm'])],
                                capture_output=True, text=True, timeout=8)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def check_environment(provider=None, *, root=ROOT, python=None, env=None, probe=inspect_runtime, which=shutil.which):
    env = read_config(root) if env is None else env
    provider = (provider or env.get('TTS_PROVIDER') or 'edge-tts').lower()
    provider = {'edge':'edge-tts', 'edge_tts':'edge-tts', 'local':'piper', 'vieneu-tts':'vieneu'}.get(provider, provider)
    if provider not in PROVIDERS:
        raise ValueError('Provider không được hỗ trợ.')
    python = python or Path(sys.executable)
    checks = []

    def add(identifier, label, status, message, remedy=''):
        checks.append(dict(id=identifier, label=label, status=status, message=message, remedy=remedy))

    for binary in ('ffmpeg', 'ffprobe'):
        found = bool(which(binary))
        add(binary, binary, 'ready' if found else 'missing',
            'Có trong PATH của server.' if found else 'Không tìm thấy trong PATH của server.',
            '' if found else 'Cài FFmpeg (gồm ffprobe), thêm vào PATH rồi khởi động lại launcher.')
    packages = probe(python)
    add('runtime', 'Python CLI/TTS', 'ready' if packages is not None else 'missing',
        'Đã kiểm tra môi trường CLI/TTS.' if packages is not None else 'Không chạy được Python CLI/TTS hoặc kiểm tra quá thời gian.',
        '' if packages is not None else 'Khôi phục .venv tại thư mục gốc theo README; môi trường API không thay thế môi trường TTS.')
    if packages is not None:
        for module in dict.fromkeys(['openai', 'dotenv', 'typer', 'rich', 'tqdm', PROVIDERS[provider]]):
            found = packages.get(module, False)
            add('dependency:' + module, 'Thư viện ' + module, 'ready' if found else 'missing',
                'Đã cài (chưa thử import/nạp thư viện).' if found else 'Chưa cài trong Python CLI/TTS.',
                '' if found else 'Cài dependency vào .venv gốc theo requirements.txt; Piper cần gói piper-tts. Sau đó kiểm tra lại.')
    numeric = [('MAX_CHUNK_CHARS', '2000'), ('TTS_CONCURRENCY', '3')]
    if provider == 'piper':
        numeric.append(('PIPER_NUM_WORKERS', '4'))
    for key, default in numeric:
        try:
            valid = int(env.get(key, default)) > 0
        except (ValueError, TypeError):
            valid = False
        add('config:' + key, key, 'ready' if valid else 'invalid',
            'Là số nguyên dương.' if valid else 'Cấu hình phải là số nguyên dương.',
            '' if valid else 'Sửa biến tương ứng trong .env hoặc môi trường server rồi kiểm tra lại.')
    for key, required in [('OPENAI_API_KEY', provider == 'openai'), ('HF_TOKEN', False)]:
        configured = bool((env.get(key) or '').strip())
        add('key:' + key, key, 'ready' if configured else ('missing' if required else 'optional'),
            'Đã cấu hình; chưa xác minh hiệu lực.' if configured else ('Chưa cấu hình.' if required else 'Chưa cấu hình; tùy chọn cho provider đang chọn.'),
            'Cấu hình ở server, không nhập key trên trang này.' if required and not configured else '')
    if provider == 'piper':
        for key, default in [('PIPER_MODEL_PATH', 'models/piper/vi_VN-vais1000-medium.onnx'),
                             ('PIPER_CONFIG_PATH', 'models/piper/vi_VN-vais1000-medium.onnx.json')]:
            path = Path(env.get(key) or default)
            path = path if path.is_absolute() else root / path
            try:
                present = path.is_file() and path.stat().st_size > 0
                if present and key == 'PIPER_CONFIG_PATH':
                    present = path.stat().st_size <= 1024 * 1024 and isinstance(json.loads(path.read_text()), dict)
            except (OSError, ValueError):
                present = False
            add('model:' + key, key, 'ready' if present else 'missing',
                'Có file không rỗng; chưa nạp model.' if present else 'File thiếu, rỗng hoặc JSON cấu hình không hợp lệ.',
                '' if present else 'Đặt model ONNX và JSON đúng đường dẫn trong .env; đường dẫn tương đối tính từ gốc project.')
        add('model_validation', 'Khả năng nạp model Piper', 'unverified', 'Cần thử giọng thật để xác minh model tương thích; T03 không nạp model.')
    elif provider == 'vieneu':
        mode = env.get('VIENEU_MODE') or 'v3turbo'
        valid_mode = mode in {'v3turbo', 'standard', 'fast', 'remote'}
        add('config:VIENEU_MODE', 'Mode VieNeu', 'ready' if valid_mode else 'invalid',
            mode if valid_mode else 'Mode không hợp lệ.', '' if valid_mode else 'Dùng v3turbo, standard, fast hoặc remote.')
        if mode == 'remote':
            try:
                url = urlsplit(env.get('VIENEU_API_BASE') or '')
                configured = url.scheme in {'http', 'https'} and bool(url.hostname) and bool((env.get('VIENEU_MODEL_NAME') or '').strip())
            except ValueError:
                configured = False
            add('remote_config', 'Kết nối VieNeu remote', 'ready' if configured else 'invalid',
                'Có endpoint và tên model; chưa gọi server.' if configured else 'Thiếu hoặc sai cấu hình remote.',
                '' if configured else 'Cấu hình VIENEU_API_BASE (http/https) và VIENEU_MODEL_NAME ở server.')
        add('model_validation', 'Model VieNeu', 'unverified', 'Chưa xác minh cache, khả năng nạp model hoặc server remote. Kiểm tra này không tải model.',
            'Nghiệm thu giọng thật ở T31; thao tác chạy thật có thể cần tải model hoặc gọi mạng.')
    else:
        add('service_validation', 'Dịch vụ giọng đọc', 'unverified', 'Chưa xác minh kết nối, quyền truy cập, quota hay giọng đọc; không gọi mạng.')
    return dict(provider=provider, status='blocked' if any(c['status'] in {'missing', 'invalid'} for c in checks) else 'checks_passed',
                runtime='project .venv', fixture=None, checks=checks,
                notice='Chỉ kiểm tra điều kiện cục bộ. Kết quả đạt không đảm bảo tạo giọng thành công. Không nạp/tải model hoặc gọi mạng.')
