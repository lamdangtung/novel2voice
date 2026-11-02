"""Telegram transport, isolated from commands and execution."""
from typing import Protocol
import httpx
import re


class Messenger(Protocol):
    def poll(self, offset: int) -> list[dict]: ...
    def send(self, chat_id: int, text: str, message_id: int | None = None) -> int: ...
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
        return self._call('getUpdates', {'offset': offset, 'timeout': 5, 'allowed_updates': ['message']})

    def send(self, chat_id, text, message_id=None):
        payload = {'chat_id': chat_id, 'text': text[:4000]}
        if message_id:
            payload['message_id'] = message_id
            try:
                return self._call('editMessageText', payload)['message_id']
            except RuntimeError:
                payload.pop('message_id')
        return self._call('sendMessage', payload)['message_id']

    def close(self):
        self.client.close()
