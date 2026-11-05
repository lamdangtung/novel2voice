"""Telegram transport, isolated from commands and execution."""
from typing import Protocol
import httpx
import re


class Messenger(Protocol):
    def poll(self, offset: int) -> list[dict]: ...
    def send(self, chat_id: int, text: str, message_id: int | None = None, *, reply_markup=None) -> int: ...
    def answer_callback(self, query_id: str) -> None: ...
    def close(self) -> None: ...


class TelegramMessenger:
    def __init__(self, token, *, client=None):
        self.token = token
        self.client = client or httpx.Client(timeout=20)

    def _safe_detail(self, value):
        detail = str(value).replace(self.token, '[redacted]')
        return re.sub(r'https?://\S+', '[URL]', detail)[:300]

    def _call(self, method, payload):
        try:
            response = self.client.post(f'https://api.telegram.org/bot{self.token}/{method}', json=payload)
        except httpx.TimeoutException as error:
            raise RuntimeError(f'Telegram {method}: timeout ({type(error).__name__}). Kiểm tra mạng/VPN/proxy.') from None
        except httpx.HTTPError as error:
            cause = error.__cause__ or error
            raise RuntimeError(f'Telegram {method}: {type(error).__name__}: {self._safe_detail(cause)}') from None
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError(f'Telegram {method}: HTTP {response.status_code}, phản hồi không phải JSON; kiểm tra mạng/proxy.') from None
        if not isinstance(data, dict):
            raise RuntimeError(f'Telegram {method}: phản hồi không hợp lệ (HTTP {response.status_code}).')
        if not data.get('ok'):
            description = data.get('description', '')
            if method == 'editMessageText' and 'message is not modified' in description:
                return {'message_id': payload['message_id']}
            code = data.get('error_code', response.status_code)
            hints = {
                401: 'Token không hợp lệ hoặc đã bị thu hồi; kiểm tra TELEGRAM_BOT_TOKEN.',
                404: 'Không tìm thấy bot/API; kiểm tra token.',
                409: 'Xung đột: có tiến trình khác polling cùng bot hoặc bot đang dùng webhook.',
                429: 'Telegram đang giới hạn số yêu cầu; chờ rồi thử lại.',
            }
            raise RuntimeError(f'Telegram {method}: HTTP {code}. {hints.get(code, "")} '
                               + self._safe_detail(description))
        return data['result']

    def identity(self):
        return self._call('getMe', {})

    def poll(self, offset):
        return self._call('getUpdates', {'offset': offset, 'timeout': 5, 'allowed_updates': ['message', 'callback_query']})

    def answer_callback(self, query_id):
        self._call('answerCallbackQuery', {'callback_query_id': query_id})

    def configure_commands(self, commands, users):
        for user in users:
            self._call('setMyCommands', {'commands': commands, 'scope': {'type': 'chat', 'chat_id': user}})

    def send(self, chat_id, text, message_id=None, *, reply_markup=None):
        # Do not silently cut results or navigation. Keep chunks below Telegram's
        # limit even for astral characters (e.g. emoji) that occupy two UTF-16 units.
        chunks, current, units = [], [], 0
        for char in text:
            width = 2 if ord(char) > 0xFFFF else 1
            if units + width > 3500:
                chunks.append(''.join(current))
                current, units = [], 0
            current.append(char)
            units += width
        chunks.append(''.join(current))
        last = None
        for index, chunk in enumerate(chunks):
            payload = {'chat_id': chat_id, 'text': chunk}
            if reply_markup is not None:
                payload['reply_markup'] = reply_markup if index == len(chunks) - 1 else {'inline_keyboard': []}
            if message_id and len(chunks) == 1:
                payload['message_id'] = message_id
                try:
                    return self._call('editMessageText', payload)['message_id']
                except RuntimeError as error:
                    if not any(reason in str(error).lower() for reason in
                               ('message to edit not found', "message can't be edited", 'message_id_invalid')):
                        raise
                    payload.pop('message_id')
            last = self._call('sendMessage', payload)['message_id']
        return last

    def close(self):
        self.client.close()
