"""Add website adapters here; the pipeline depends only on NovelSource."""
from .base import NovelSource
from .ixdzs8 import Ixdzs8Source


def get_novel_source(url: str) -> NovelSource:
    source = Ixdzs8Source()
    if source.supports(url):
        return source
    source.close()
    raise ValueError('Chưa hỗ trợ nguồn URL này. Hiện hỗ trợ trang chương ixdzs8.com.')
