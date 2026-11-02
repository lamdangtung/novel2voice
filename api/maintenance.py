"""Cooperating API/worker/backup maintenance gate; OS releases locks on crash."""
from contextlib import contextmanager
import fcntl
from api.books import BookError,safe_directory
from api.configuration import check_path

@contextmanager
def gate(root,exclusive=False):
    root=safe_directory(root);path=root/'maintenance.lock';check_path(path)
    with path.open('a') as stream:
        try:fcntl.flock(stream,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:raise BookError('Thư viện đang được sử dụng hoặc bảo trì. Dừng app/worker rồi thử lại.',503)
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)
