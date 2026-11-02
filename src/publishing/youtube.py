"""YouTube Data API resumable transport using Google's OAuth session."""
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .base import UploadProgress, RetryableUploadError
from .auth import authorized_session, save_token
from .schedule import require_future, normalize_publish_at


class YouTubePublisher:
    def __init__(self, *, token_path: Path, session=None):
        self.token_path = token_path
        self.http = session if session is not None else authorized_session(token_path)
        self._owns_session = session is None

    def _request(self, method, url, **kwargs):
        try:
            response = self.http.request(method, url, timeout=(15, 120), allow_redirects=False, **kwargs)
        except requests.RequestException:
            # Never print session URLs or access tokens in exception messages.
            raise RetryableUploadError('Kết nối YouTube gián đoạn; có thể chạy lại để tiếp tục.') from None
        if response.status_code in (408, 429, 500, 502, 503, 504):
            raise RetryableUploadError(f'YouTube tạm thời trả HTTP {response.status_code}.')
        if response.status_code >= 400:
            reason = 'unknown'
            try:
                details = response.json().get('error', {}).get('errors', [])
                if details:
                    reason = re.sub(r'[^a-zA-Z0-9_-]', '', str(details[0].get('reason', 'unknown')))[:80]
            except (ValueError, AttributeError, TypeError):
                pass
            raise RuntimeError(f'YouTube HTTP {response.status_code} ({reason}). '
                               'Nếu phiên upload hết hạn, kiểm tra YouTube Studio trước khi tạo lần upload mới.')
        return response

    def channel_id(self):
        response = self._request('GET', 'https://www.googleapis.com/youtube/v3/channels',
                                 params={'part': 'id', 'mine': 'true'})
        items = response.json().get('items', [])
        if len(items) != 1:
            raise ValueError('Tài khoản OAuth cần xác định đúng một kênh YouTube. Đăng nhập lại và chọn kênh.')
        return items[0]['id']

    def _validate_session(self, session):
        parts = urlsplit(session)
        if (parts.scheme != 'https' or parts.hostname not in {'www.googleapis.com', 'youtube.googleapis.com'}
                or parts.username or parts.password or parts.port not in (None, 443)
                or not parts.path.startswith('/upload/youtube/v3/videos')):
            raise ValueError('Địa chỉ phiên upload YouTube không hợp lệ.')

    def start(self, spec, size):
        if spec.publish_at is not None:
            require_future(spec.publish_at)
            if spec.privacy != 'private':
                raise ValueError('Lên lịch YouTube cần privacy=private.')
        body = {'snippet': {'title': spec.title, 'description': spec.description,
                             'tags': list(spec.tags), 'categoryId': spec.category_id},
                'status': {'privacyStatus': spec.privacy, 'selfDeclaredMadeForKids': spec.made_for_kids}}
        if spec.publish_at is not None:
            body['status']['publishAt'] = normalize_publish_at(spec.publish_at)
        if spec.default_language is not None:
            body['snippet']['defaultLanguage'] = spec.default_language
        if spec.default_audio_language is not None:
            body['snippet']['defaultAudioLanguage'] = spec.default_audio_language
        if spec.contains_synthetic_media is not None:
            body['status']['containsSyntheticMedia'] = spec.contains_synthetic_media
        response = self._request('POST', 'https://www.googleapis.com/upload/youtube/v3/videos',
            params={'uploadType': 'resumable', 'part': 'snippet,status',
                    'notifySubscribers': str(spec.notify_subscribers).lower()}, json=body,
            headers={'X-Upload-Content-Length': str(size), 'X-Upload-Content-Type': 'video/mp4'})
        if response.status_code not in (200, 201) or 'Location' not in response.headers:
            raise ValueError('YouTube không trả phiên upload.')
        session = response.headers['Location']
        self._validate_session(session)
        return session

    def _progress(self, response, size):
        if response.status_code in (200, 201):
            data = response.json()
            video_id = data.get('id', '')
            if not re.fullmatch(r'[a-zA-Z0-9_-]{11}', video_id):
                raise ValueError('YouTube không trả video ID hợp lệ; không tự upload lại để tránh trùng.')
            return UploadProgress(size, video_id, data.get('status', {}).get('privacyStatus'))
        if response.status_code == 308:
            value = response.headers.get('Range')
            if not value:
                return UploadProgress(0)
            match = re.fullmatch(r'bytes=0-([0-9]+)', value)
            if not match or int(match[1]) >= size:
                raise ValueError('YouTube trả byte range không hợp lệ.')
            return UploadProgress(int(match[1]) + 1)
        raise ValueError(f'Phản hồi upload bất thường: HTTP {response.status_code}.')

    def query(self, session, size):
        self._validate_session(session)
        response = self._request('PUT', session, data=b'',
            headers={'Content-Length': '0', 'Content-Range': f'bytes */{size}'})
        return self._progress(response, size)

    def send(self, session, data, offset, size):
        self._validate_session(session)
        response = self._request('PUT', session, data=data, headers={
            'Content-Type': 'video/mp4', 'Content-Length': str(len(data)),
            'Content-Range': f'bytes {offset}-{offset + len(data) - 1}/{size}'})
        return self._progress(response, size)

    def set_thumbnail(self, video_id, thumbnail):
        from PIL import Image
        with Image.open(thumbnail) as image:
            mime = 'image/png' if image.format == 'PNG' else 'image/jpeg'
        # A byte payload is replayable if AuthorizedSession refreshes OAuth after a 401.
        self._request('POST', 'https://www.googleapis.com/upload/youtube/v3/thumbnails/set',
                      params={'videoId': video_id, 'uploadType': 'media'},
                      headers={'Content-Type': mime}, data=Path(thumbnail).read_bytes())

    def close(self):
        if self._owns_session:
            try:
                save_token(self.http.credentials, self.token_path)
            finally:
                self.http.close()
