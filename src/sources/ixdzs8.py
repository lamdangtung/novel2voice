"""Chapter adapter for ixdzs8.com; selectors stay out of the pipeline."""
import re
import time
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .base import Chapter


class Ixdzs8Source:
    def __init__(self, *, client=None, request_interval=1.0):
        if request_interval < 0:
            raise ValueError('request_interval phải >= 0.')
        self.client = client if client is not None else httpx.Client(
            timeout=30, follow_redirects=False,
            headers={'User-Agent': 'novel2voice/1.0 (chapter reader)'})
        self._owns_client = client is None
        self.request_interval = request_interval
        self._last_request = None

    def _identity(self, url):
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname not in {'ixdzs8.com', 'www.ixdzs8.com'}
                or parts.username or parts.password or parts.port not in (None, 443)
                or parts.query or parts.fragment):
            raise ValueError('URL phải là trang chương HTTPS trên ixdzs8.com.')
        match = re.fullmatch(r'/read/([0-9]+)/p([1-9][0-9]*)\.html', parts.path)
        if not match:
            raise ValueError('URL chương cần có dạng https://ixdzs8.com/read/<book>/p<number>.html.')
        return match.groups()

    def supports(self, url):
        try:
            self._identity(url)
            return True
        except ValueError:
            return False

    def fetch_chapter(self, url):
        self._identity(url)
        for redirect in range(4):
            if self._last_request is not None:
                time.sleep(max(0, self.request_interval - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            response = self.client.get(url)
            if response.is_redirect:
                target = urljoin(url, response.headers.get('location', ''))
                if self._identity(target) != self._identity(url):
                    raise ValueError('Redirect sang chương khác không được hỗ trợ.')
                url = target
                continue
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError('HTML chương vượt giới hạn 2 MB.')
            response.encoding = 'utf-8'
            return self.parse_chapter(response.text, url)
        raise ValueError('Trang truyện redirect quá nhiều lần.')

    def parse_chapter(self, html, url):
        book_id, chapter_id = self._identity(url)
        soup = BeautifulSoup(html, 'html.parser')
        heading = soup.select_one('h1.page-d-name')
        section = soup.select_one('article.page-content section')
        if heading is None or section is None:
            raise ValueError('Không tìm thấy tiêu đề/nội dung chương; trang có thể đổi cấu trúc hoặc bị chặn.')
        for noise in section.select('script, style, iframe, ins, nav, aside, .ad, .ads, .advertisement'):
            noise.decompose()
        paragraphs = [' '.join(p.get_text(' ', strip=True).split()) for p in section.select('p')]
        text = '\n\n'.join(p for p in paragraphs if p)
        title = ' '.join(heading.get_text(' ', strip=True).split())
        if not title or not text:
            raise ValueError('Tiêu đề hoặc nội dung chương rỗng.')
        link = soup.select_one('a.chapter-next[href], a.read-prog-next[href], .read-next[data-url]')
        next_url = None
        if link:
            target = urljoin(url, link.get('href') or link.get('data-url'))
            # The final chapter can link to the book's contents page.
            if self.supports(target):
                next_book, next_id = self._identity(target)
                if next_book != book_id or int(next_id) <= int(chapter_id):
                    raise ValueError('Liên kết chương tiếp theo trỏ sai truyện hoặc lùi chương.')
                next_url = target
            else:
                parts = urlsplit(target)
                if (parts.scheme != 'https' or parts.hostname not in {'ixdzs8.com', 'www.ixdzs8.com'}
                        or parts.path != f'/read/{book_id}/' or parts.query or parts.fragment):
                    raise ValueError('Liên kết chương tiếp theo không hợp lệ hoặc chưa được hỗ trợ.')
        return Chapter('ixdzs8', book_id, chapter_id, title, text, url, 'zh', next_url)

    def close(self):
        if self._owns_client:
            self.client.close()
