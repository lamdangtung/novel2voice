"""Button navigation and durable guided input, above the command controller.

This adapter delegates all queue mutations to the existing authorized controller.
Wizard state and the response receipt commit together; confirmed actions use a
stable request ID so replay after a crash cannot enqueue another daily batch.
"""
import json
import secrets
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .controller import HELP, format_job

LABELS = {'queued': 'Chờ chạy', 'running': 'Đang chạy', 'failed': 'Lỗi',
          'interrupted': 'Bị ngắt', 'succeeded': 'Hoàn thành', 'cancelled': 'Đã hủy'}
GROUPS = {'all': 'Tất cả', 'active': 'Đang xử lý / chờ', 'failed': 'Cần xử lý', 'done': 'Đã kết thúc'}
COMMANDS = [
    {'command': 'menu', 'description': 'Mở bảng điều khiển'},
    {'command': 'new', 'description': 'Chạy hoặc hẹn giờ một chương'},
    {'command': 'plan', 'description': 'Lên lịch 5 chương mỗi ngày'},
    {'command': 'status', 'description': 'Danh sách job và tiến độ'},
    {'command': 'stories', 'description': 'Các truyện đã cấu hình'},
    {'command': 'help', 'description': 'Hướng dẫn và lệnh gõ tay'},
    {'command': 'abort', 'description': 'Thoát thao tác đang nhập'},
]


def button(text, data):
    return {'text': text, 'callback_data': data}


def view(text, rows=()):
    return {'text': text, 'reply_markup': {'inline_keyboard': list(rows)}}


class TelegramUI:
    def __init__(self, controller):
        self.controller = controller
        self.store = controller.store
        self.state = None  # Only the polling thread handles interaction state.

    def identity(self, update):
        callback = update.get('callback_query')
        message = callback.get('message', {}) if isinstance(callback, dict) else update.get('message', {})
        user = callback.get('from', {}) if isinstance(callback, dict) else message.get('from', {})
        chat = message.get('chat', {})
        if (chat.get('type') != 'private' or user.get('id') not in self.controller.allowed_users
                or user.get('is_bot') or chat.get('id') != user.get('id')):
            return None
        return user['id']

    def handle(self, update):
        user = self.identity(update)
        if user is None:
            return None
        cached = self.store.ui_receipt(update['update_id'])
        if cached is not None:
            return user, cached
        self.state = self.store.ui_state(user)
        if self.state and self.state['expires'] < time.time():
            self.state = None
        try:
            if 'callback_query' in update:
                response = self._callback(update['callback_query'].get('data', ''), user)
            else:
                text = update.get('message', {}).get('text', '')
                response = self._message(text if isinstance(text, str) else '', user, update['update_id'])
        except (ValueError, IndexError, KeyError) as error:
            response = view('Chưa thể thực hiện: ' + (str(error) or 'Thông tin không hợp lệ.')
                            + '\nBạn có thể sửa thông tin hoặc về menu.', self._navigation())
        self.store.ui_commit(user, self.state, update['update_id'], response)
        return user, response

    def _navigation(self):
        rows = []
        if self.state and self.state.get('history'):
            rows.append([button('‹ Quay lại', 'back:' + self.state['token'])])
        rows.append([button('Về menu / bỏ thao tác', 'home')])
        return rows

    def _save(self, state):
        self.state = dict(state, token=secrets.token_hex(6), expires=time.time() + 1800)

    def _advance(self, **changes):
        old = dict(self.state)
        history = old.pop('history', [])
        self._save(dict(self.state, **changes, history=history + [old]))

    def _home(self, user=None):
        self.state = None
        counts = self.store.summary(user) if user is not None else {}
        summary = (f"Đang chạy: {counts.get('running', 0)} · Chờ: {counts.get('queued', 0)} · "
                   f"Cần xử lý: {counts.get('failed', 0) + counts.get('interrupted', 0)}\n")
        return view('novel2voice · Bảng điều khiển\n'
                    'Mỗi chương tạo một video. Chọn thao tác bên dưới.\n'
                    'Tất cả ngày giờ dùng giờ Việt Nam.\n\n'
                    + summary + self._pause(), [
            [button('▶ Chạy / hẹn giờ', 'new'), button('🗓 5 chương/ngày', 'flow:daily')],
            [button('📋 Job & tiến độ', 'jobs:all:1'), button('📚 Truyện', 'stories')],
            [button('Dọn lịch sử', 'cleanup'), button('Hướng dẫn', 'help')]])

    def _pause(self):
        pause = self.store.upload_pause_until()
        if pause > time.time():
            stamp = datetime.fromtimestamp(pause, ZoneInfo(self.controller.timezone)).strftime('%d/%m/%Y %H:%M')
            return f'⏸ Upload YouTube tạm giữ đến khoảng {stamp}. Đây là mốc thử lại, chưa bảo đảm kênh hết giới hạn.\n'
        return ''

    def _new(self):
        self.state = None
        return view('Bạn muốn bắt đầu lúc nào?\nHẹn giờ ở đây là giờ bắt đầu xử lý, không phải giờ công khai YouTube.', [
            [button('Chạy ngay', 'flow:run')], [button('Hẹn giờ bắt đầu', 'flow:schedule')],
            [button('Về menu', 'home')]])

    def _begin(self, action, *, step='story', **values):
        self._save(dict(action=action, step=step, history=[], request_id=-(secrets.randbelow(2**60) + 1), **values))
        return self._prompt()

    def _prompt(self):
        state = self.state
        step, action = state['step'], state['action']
        if step == 'story':
            keys = list(self.controller.profiles)
            page = state.get('story_page', 0)
            rows = [[button(name, f'pick:{state["token"]}:{i}')] for i, name in enumerate(keys) if page * 8 <= i < (page + 1) * 8]
            nav = []
            if page:
                nav.append(button('‹ Trước', f'storiespage:{state["token"]}:{page - 1}'))
            if (page + 1) * 8 < len(keys):
                nav.append(button('Sau ›', f'storiespage:{state["token"]}:{page + 1}'))
            return view('Bước 1 · Chọn truyện', rows + ([nav] if nav else []) + self._navigation())
        if step == 'chapter':
            return view(f'Truyện: {state["story"]}\n'
                        + ('Nhập chương đầu tiên (ví dụ: 21).' if action == 'daily' else 'Nhập số chương (ví dụ: 21).'), self._navigation())
        if step == 'time':
            tomorrow = (datetime.now(ZoneInfo(self.controller.timezone)) + timedelta(days=1)).strftime('%Y-%m-%d')
            title = 'giờ công khai YouTube mới' if action == 'retry' else 'giờ bắt đầu xử lý'
            return view(f'Nhập {title} theo giờ Việt Nam:\nYYYY-MM-DD HH:MM\nVí dụ: {tomorrow} 19:30'
                        + ('\nCần cách hiện tại hơn 15 phút; chừa đủ thời gian upload và chờ giới hạn kênh.' if action == 'retry' else ''), self._navigation())
        if step == 'date':
            tomorrow = (datetime.now(ZoneInfo(self.controller.timezone)) + timedelta(days=1)).strftime('%Y-%m-%d')
            return view(f'Nhập ngày công khai đầu tiên: YYYY-MM-DD\nVí dụ: {tomorrow}', self._navigation())
        if step == 'days':
            return view('Chọn số ngày · 5 chương/ngày\nHoặc nhập số từ 1 đến 7.', [
                [button(f'{n} ngày', f'days:{state["token"]}:{n}') for n in (1, 3, 7)]] + self._navigation())
        if step == 'ids':
            return view('Nhập các ID job cần hủy, cách nhau bằng khoảng trắng.\nVí dụ: 20 21 22\nChỉ hủy job đang chờ của bạn.', self._navigation())
        if step == 'confirm':
            return view(state['preview'] + '\n\nChỉ thực hiện sau khi bạn xác nhận.', [
                [button('✓ Xác nhận', 'confirm:' + state['token'])]] + self._navigation())
        raise ValueError('Thao tác đã hết hạn. Mở /menu để bắt đầu lại.')

    def _draft(self, command, preview, *, initial=False):
        if initial:
            self._save(dict(self.state, step='confirm', command=command, preview=preview, history=[]))
        else:
            self._advance(step='confirm', command=command, preview=preview)
        return self._prompt()

    def _execute(self, command, user, request_id):
        update = {'update_id': request_id, 'message': {'text': command,
                  'from': {'id': user}, 'chat': {'id': user, 'type': 'private'}}}
        return self.controller.handle(update)[1]

    def _input(self, text, user):
        state = self.state
        step, action = state['step'], state['action']
        if step == 'chapter':
            chapter = int(text)
            if not 1 <= chapter <= 1_000_000:
                raise ValueError('Số chương từ 1 đến 1000000.')
            base = f'/{action} {state["story"]} {chapter}'
            if action == 'run':
                self._advance(chapter=chapter)
                settings = self.controller.profiles[state['story']]
                output = 'Upload YouTube · ' + settings.get('youtube_privacy', 'private') if settings.get('upload_youtube', True) else 'Chỉ tạo video trên máy'
                return self._draft(base, f'Chạy {state["story"]} · Chương {chapter}\n{output}\nJob xếp hàng nếu máy đang bận.\n' + self._pause())
            self._advance(chapter=chapter, step='date' if action == 'daily' else 'time')
            return self._prompt()
        if step == 'time':
            instant = datetime.strptime(text, '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(self.controller.timezone))
            if instant.timestamp() <= time.time() + (900 if action == 'retry' else 0):
                raise ValueError('Giờ phải ở tương lai' + (' và cách hiện tại hơn 15 phút.' if action == 'retry' else '.'))
            command = f'/retry {state["job_id"]} {text}' if action == 'retry' else f'/schedule {state["story"]} {state["chapter"]} {text}'
            what = f'Đổi giờ công khai và retry job #{state["job_id"]}' if action == 'retry' else f'Hẹn chạy {state["story"]} · Chương {state["chapter"]}'
            return self._draft(command, f'{what}\n{text} · giờ Việt Nam\n' + self._pause())
        if step == 'date':
            datetime.strptime(text, '%Y-%m-%d')
            self._advance(date=text, step='days')
            return self._prompt()
        if step == 'days':
            from .scheduling import plan_daily, DEFAULT_PUBLISH_TIMES
            days = int(text)
            settings = self.controller.profiles[state['story']]
            plan = plan_daily(state['chapter'], state['date'], days,
                              times=settings.get('daily_publish_times', DEFAULT_PUBLISH_TIMES), timezone=self.controller.timezone)
            rows = []
            for chapter, stamp in plan:
                instant = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(ZoneInfo(self.controller.timezone))
                rows.append(f'Chương {chapter} → {instant:%d/%m %H:%M}')
            command = f'/schedule-day {state["story"]} {state["chapter"]} {state["date"]} {days}'
            return self._draft(command, f'{state["story"]} · {len(plan)} chương / {days} ngày\n'
                               + '\n'.join(rows) + '\nGiờ công khai YouTube · giờ Việt Nam.\nBot chuẩn bị trong 24 giờ trước mỗi mốc.\n' + self._pause())
        if step == 'ids':
            ids = list(dict.fromkeys(int(value) for value in text.split()))
            if not ids or len(ids) > 50 or any(i < 1 for i in ids):
                raise ValueError('Nhập từ 1 đến 50 ID dương, cách nhau bằng khoảng trắng.')
            return self._draft('/cancel ' + ' '.join(map(str, ids)), 'Hủy các job: ' + ', '.join(map(str, ids))
                               + '\nJob đang chạy hoặc không thuộc bạn sẽ được bỏ qua.')
        return view('Hãy dùng các nút bên dưới để tiếp tục.', self._prompt()['reply_markup']['inline_keyboard'])

    def _jobs(self, user, group='all', page=1):
        self.state = None
        if group not in GROUPS or page < 1:
            raise ValueError('Trang hoặc bộ lọc không hợp lệ.')
        jobs, total = self.store.list_page(user, page, group=group)
        pages = max(1, (total + 9) // 10)
        if page > pages:
            return self._jobs(user, group, pages)
        lines = [self._pause() + f'{GROUPS[group]} · Trang {page}/{pages} · {total} job']
        rows = [[button('Tất cả', 'jobs:all:1'), button('Đang chờ/chạy', 'jobs:active:1')],
                [button('Cần xử lý', 'jobs:failed:1'), button('Đã kết thúc', 'jobs:done:1')]]
        for job in jobs:
            progress = json.loads(job['progress'])
            suffix = f' · ~{progress["overall"]:.0%}' if job['status'] == 'running' and 'overall' in progress else ''
            lines.append(f'#{job["id"]} · {job["profile"][:40]} · Chương {job["chapter"]}\n{LABELS[job["status"]]}{suffix}')
        rows += [[button(f'#{j["id"]} · Chương {j["chapter"]}', f'job:{j["id"]}') for j in jobs[i:i+2]] for i in range(0, len(jobs), 2)]
        if not jobs:
            lines.append('Không có job trong nhóm này. Chọn nhóm khác hoặc tạo job mới.')
        nav = []
        if page > 1:
            nav.append(button('‹ Trước', f'jobs:{group}:{page - 1}'))
        nav.append(button('↻ Làm mới', f'jobs:{group}:{page}'))
        if page < pages:
            nav.append(button('Sau ›', f'jobs:{group}:{page + 1}'))
        rows += [nav, [button('Tạo job', 'new'), button('Hủy nhiều job', 'cancelmany')], [button('Về menu', 'home')]]
        return view('\n\n'.join(lines), rows)

    def job_view(self, job):
        rows = [[button('↻ Cập nhật', f'job:{job["id"]}')]]
        status, job_id = job['status'], job['id']
        if status == 'queued':
            rows.append([button('▶ Chạy ngay', f'action:now:{job_id}'), button('Hủy job', f'action:cancel:{job_id}')])
        if status in {'failed', 'interrupted'}:
            rows.append([button('▶ Retry ngay', f'action:now:{job_id}')])
            actions = [button('Thử lại theo lịch', f'action:retry:{job_id}')]
            if json.loads(job['settings']).get('upload_youtube', True):
                actions.append(button('Đổi giờ publish', f'action:retime:{job_id}'))
            rows.append(actions)
        if status in {'succeeded', 'cancelled', 'failed', 'interrupted'} and not job.get('cleared'):
            rows.append([button('Dọn khỏi danh sách', f'action:clear:{job_id}')])
        if job.get('result'):
            for url in json.loads(job['result']).get('youtube', [])[:1]:
                if url.startswith('https://www.youtube.com/watch?v='):
                    rows.append([{'text': 'Mở video YouTube', 'url': url}])
        rows.append([button('Danh sách job', 'jobs:all:1'), button('Về menu', 'home')])
        return view(self._pause() + format_job(job, self.controller.timezone), rows)

    def _callback(self, data, user):
        if not isinstance(data, str) or len(data.encode()) > 64:
            raise ValueError('Nút không hợp lệ.')
        parts = data.split(':')
        action = parts[0]
        if data == 'home':
            return self._home(user)
        if data == 'new':
            return self._new()
        if data == 'stories':
            return self._stories()
        if data == 'help':
            self.state = None
            return view('Dùng /menu để thao tác bằng nút. /abort để thoát bước đang nhập.\n\n' + HELP, [[button('Về menu', 'home')]])
        if data == 'cleanup':
            self.state = None
            return view('Dọn lịch sử của bạn\nGiữ file và video YouTube. Job đang chờ/chạy không bị dọn.', [
                [button('Hoàn thành / đã hủy', 'clean:finished')], [button('Lỗi / bị ngắt', 'clean:failed')], [button('Về menu', 'home')]])
        if data == 'cancelmany':
            return self._begin('cancel', step='ids')
        if action == 'clean' and len(parts) == 2 and parts[1] in {'finished', 'failed'}:
            self._begin('clear')
            return self._draft('/clear ' + parts[1], 'Dọn toàn bộ job ' + ('hoàn thành/đã hủy' if parts[1] == 'finished' else 'lỗi/bị ngắt')
                               + ' của bạn.\nGiữ file và video YouTube; có thể xem lại bằng ID.', initial=True)
        if action == 'flow' and len(parts) == 2 and parts[1] in {'run', 'schedule', 'daily'}:
            return self._begin(parts[1])
        if action == 'jobs' and len(parts) == 3:
            return self._jobs(user, parts[1], int(parts[2]))
        if action in {'job', 'action'}:
            job_id = int(parts[-1])
            job = self.store.get(job_id, user)
            if not job:
                raise ValueError('Không tìm thấy job của bạn.')
            if action == 'job' and len(parts) == 2:
                self.state = None
                return self.job_view(job)
            if len(parts) != 3 or parts[1] not in {'cancel', 'retry', 'retime', 'clear', 'now'}:
                raise ValueError('Nút không hợp lệ.')
            task = parts[1]
            allowed = {'now': {'queued', 'failed', 'interrupted'}, 'cancel': {'queued'}, 'retry': {'failed', 'interrupted'},
                       'retime': {'failed', 'interrupted'}, 'clear': {'succeeded', 'cancelled', 'failed', 'interrupted'}}
            if job['status'] not in allowed[task]:
                return self.job_view(job)
            if task == 'retime':
                return self._begin('retry', step='time', job_id=job_id)
            self._begin(task, job_id=job_id)
            return self._draft(f'/{task} {job_id}', f'{ {"cancel": "Hủy", "retry": "Thử lại", "clear": "Dọn", "now": "Chạy/retry ngay"}[task]} job #{job_id} · Chương {job["chapter"]}'
                               + ('\nGiữ giờ publish cũ. Nếu đã trễ, chọn Đổi giờ publish trong chi tiết job.' if task == 'retry' else '')
                               + ('\nGiữ file và video/lịch YouTube.' if task == 'clear' else '')
                               + ('\nBỏ giờ chờ, cửa sổ 24 giờ, cooldown upload và lịch publish. Upload private, không đặt lịch. Vẫn giữ giới hạn LLM. Nếu máy đang bận, chờ job hiện tại xong. YouTube vẫn có thể từ chối upload.' if task == 'now' else ''), initial=True)
        if action in {'pick', 'storiespage', 'days', 'back', 'confirm'}:
            if not self.state or len(parts) < 2 or parts[1] != self.state['token']:
                return view('Nút này đã cũ hoặc thao tác đã hết hạn. Mở menu để tiếp tục.', [[button('Mở menu', 'home')]])
            if action == 'back' and len(parts) == 2:
                history = self.state.get('history', [])
                if history:
                    self._save(dict(history[-1], history=history[:-1]))
                return self._prompt()
            if action == 'pick' and len(parts) == 3 and self.state['step'] == 'story':
                index = int(parts[2])
                if not 0 <= index < len(self.controller.profiles):
                    raise ValueError('Truyện không hợp lệ.')
                story = list(self.controller.profiles)[index]
                if self.state['action'] == 'daily' and not self.controller.profiles[story].get('upload_youtube', True):
                    raise ValueError('Truyện này tắt upload YouTube; chọn truyện khác hoặc Chạy ngay.')
                self._advance(story=story, step='chapter')
                return self._prompt()
            if action == 'storiespage' and len(parts) == 3 and self.state['step'] == 'story':
                page = int(parts[2])
                if not 0 <= page < (len(self.controller.profiles) + 7) // 8:
                    raise ValueError('Trang không hợp lệ.')
                self._advance(story_page=page)
                return self._prompt()
            if action == 'days' and len(parts) == 3 and self.state['step'] == 'days':
                return self._input(parts[2], user)
            if action == 'confirm' and len(parts) == 2 and self.state['step'] == 'confirm':
                response = self._execute(self.state['command'], user, self.state['request_id'])
                job_id = self.state.get('job_id')
                self.state = None
                rows = [[button('Danh sách job', 'jobs:all:1'), button('Về menu', 'home')]]
                if job_id:
                    rows.insert(0, [button('Xem job', f'job:{job_id}')])
                return view(response, rows)
        raise ValueError('Nút không hợp lệ. Mở /menu để tiếp tục.')

    def _stories(self):
        self.state = None
        lines = ['Các truyện đã cấu hình']
        for name, entry in list(self.controller.profiles.items())[:20]:
            output = 'YouTube · ' + entry.get('youtube_privacy', 'private') if entry.get('upload_youtube', True) else 'Chỉ tạo video trên máy'
            lines.append(f'{name} · {output}')
        if len(self.controller.profiles) > 20:
            lines.append('Danh sách rút gọn; chọn Tạo job để duyệt tất cả truyện.')
        return view('\n\n'.join(lines), [[button('Tạo job', 'new'), button('5 chương/ngày', 'flow:daily')], [button('Về menu', 'home')]])

    def _message(self, text, user, update_id):
        text = text.strip()
        parts = text.split()
        command = parts[0].split('@')[0] if parts else ''
        if command in {'/start', '/menu', '/abort'}:
            return self._home(user)
        if command == '/new':
            return self._new()
        if command == '/plan':
            return self._begin('daily')
        if command == '/help':
            return self._callback('help', user)
        if command == '/stories':
            return self._stories()
        if command == '/status':
            if len(parts) == 1:
                return self._jobs(user)
            if len(parts) == 3 and parts[1] == 'page':
                return self._jobs(user, page=int(parts[2]))
            if len(parts) == 2:
                job = self.store.get(int(parts[1]), user)
                if job:
                    self.state = None
                    return self.job_view(job)
                raise ValueError('Không tìm thấy job của bạn.')
            raise ValueError('Dùng /status, /status page 2 hoặc /status 20.')
        if not text.startswith('/'):
            if self.state:
                try:
                    return self._input(text.strip(), user)
                except ValueError:
                    prompt = self._prompt()
                    return view('Thông tin chưa hợp lệ. Hãy nhập lại theo hướng dẫn.\n\n' + prompt['text'], prompt['reply_markup']['inline_keyboard'])
            return view('Chọn một thao tác để bắt đầu.', [[button('Mở menu', 'home')]])
        if len(parts) == 1:
            shortcuts = {'/run': 'flow:run', '/schedule': 'flow:schedule', '/schedule-day': 'flow:daily',
                         '/cancel': 'cancelmany', '/clear': 'cleanup', '/retry': 'jobs:failed:1'}
            if command in shortcuts:
                return self._callback(shortcuts[command], user)
        supported = {'/run', '/schedule', '/schedule-day', '/cancel', '/retry', '/clear', '/now'}
        if command not in supported:
            return view('Không nhận ra lệnh. Dùng menu hoặc xem hướng dẫn.', [[button('Mở menu', 'home'), button('Hướng dẫn', 'help')]])
        self.state = None
        response = self._execute(text, user, update_id)
        if response == HELP or response.startswith('Lệnh không hợp lệ'):
            examples = {
                '/run': '/run <truyện> <chương>',
                '/schedule': '/schedule <truyện> <chương> YYYY-MM-DD HH:MM (giờ bắt đầu xử lý)',
                '/schedule-day': '/schedule-day <truyện> <chương_đầu> YYYY-MM-DD [số_ngày]',
                '/cancel': '/cancel 20 21 22',
                '/retry': '/retry <job_id> hoặc /retry <job_id> YYYY-MM-DD HH:MM (giờ công khai mới)',
                '/now': '/now <job_id>',
                '/clear': '/clear <job_id> hoặc /clear finished hoặc /clear failed',
            }
            response = 'Thông tin chưa đúng hoặc không tìm thấy job/truyện.\nCú pháp: ' + examples[command] + '\nBạn cũng có thể dùng nút trong menu.'
        return view(response, [[button('Job & tiến độ', 'jobs:all:1'), button('Về menu', 'home')]])
