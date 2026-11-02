"""Transaction-scoped chapter reservations for queued and active jobs."""
import json
from sqlmodel import select
from api.storage.models import Job
from api.books import BookError


def check_conflicts(db,job):
    plan=json.loads(job.config_json).get('plan',{})
    targets={item['id'] for item in plan.get('chapters',[])}
    if not targets:return
    for other in db.exec(select(Job).where(Job.book_id==job.book_id,Job.id!=job.id,Job.status.in_(['queued','running','stop_requested']))).all():
        existing=json.loads(other.config_json).get('plan',{})
        if targets.intersection(item['id'] for item in existing.get('chapters',[])):
            raise BookError(f'Chương đang được công việc {other.id} sử dụng. Chờ hoàn tất hoặc dừng công việc đó rồi thử lại.',409)
