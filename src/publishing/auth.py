"""Explicit local OAuth login; uploading never opens a browser implicitly."""
import os
import tempfile
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']


def save_token(credentials, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(credentials.to_json())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def login(client_secrets: Path, token_path: Path):
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not Path(client_secrets).is_file():
        raise ValueError('Chưa có OAuth client JSON. Tạo OAuth client loại Desktop app trong Google Cloud.')
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    credentials = flow.run_local_server(host='localhost', port=0, access_type='offline', prompt='consent')
    save_token(credentials, token_path)


def authorized_session(token_path):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import AuthorizedSession, Request
    if not Path(token_path).is_file():
        raise ValueError('Chưa đăng nhập YouTube. Chạy: python -m src.main youtube-auth')
    credentials = Credentials.from_authorized_user_file(str(token_path))
    if not credentials.has_scopes(SCOPES):
        raise ValueError('OAuth token thiếu quyền. Chạy lại youtube-auth.')
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError('OAuth token hết hạn. Chạy lại youtube-auth.')
        credentials.refresh(Request())
        save_token(credentials, token_path)
    return AuthorizedSession(credentials)
