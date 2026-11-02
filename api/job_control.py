"""T19 cooperative stop/requeue of the same immutable job snapshot."""
import json
from uuid import UUID
from fastapi import Request
from sqlalchemy import text
from api.books import BookError, safe_directory
from api.storage import session_scope
from api.storage.models import Job,Chapter,Artifact
from api.configuration import check_path
from api.verification.workspace import atomic_json


def stop_requested(repo,job_id):
    with session_scope(repo.engine) as db:
        job=db.get(Job,str(job_id))
        return job is not None and job.status=='stop_requested'


def stop(repo,job_id):
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));job=db.get(Job,str(job_id))
        if not job:raise BookError('Không tìm thấy tác vụ.',404)
        if job.status in {'completed','failed','stopped','interrupted','stop_requested'}:return {'id':job.id,'status':job.status}
        if job.status not in {'queued','running'}:raise BookError('Tác vụ chưa bắt đầu để dừng.')
        job.status='stopped' if job.status=='queued' else 'stop_requested';db.add(job)
        result={'id':job.id,'status':job.status}
    if result['status']=='stopped':
        folder=safe_directory(repo.root/'job-results'/str(job_id))
        atomic_json(folder/'report.json',{'status':'stopped','steps':0,'completed_steps':0,'notice':'Đã dừng trước khi worker nhận job.'})
    return result


def resume(repo,job_id):
    folder=repo.root/'job-results'/str(job_id);marker=folder/'resume-state.json';check_path(marker)
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));job=db.get(Job,str(job_id))
        if not job:raise BookError('Không tìm thấy tác vụ.',404)
        if job.status in {'queued','running'} and marker.is_file():return {'id':job.id,'status':job.status}
        if job.status not in {'stopped','interrupted'}:raise BookError('Chỉ tiếp tục tác vụ đã dừng/gián đoạn; nội dung phải khớp snapshot.')
        from api.recovery import bridge_alive
        if bridge_alive(repo,job_id):raise BookError('Tiến trình TTS cũ đang dừng an toàn; chờ rồi thử tiếp tục lại.')
        config=json.loads(job.config_json)
        for item in config.get('plan',{}).get('chapters',[]):
            chapter=db.get(Chapter,item['id'])
            if not chapter or chapter.source_hash!=item.get('sha256') or chapter.revision!=item.get('revision'):
                raise BookError('Nội dung đã đổi khi job dừng; cần xem kế hoạch mới.')
            if job.kind=='process':
                stage=folder/('chapters/'+item['id'] if len(config['plan']['chapters'])>1 else '')/'translation-stage.json';check_path(stage)
                if stage.is_file():
                    data=json.loads(stage.read_text());artifact=db.get(Artifact,data.get('artifact_id'))
                    if not artifact or not artifact.verified:raise BookError('Bản dịch đã đổi khi job dừng; cần đối chiếu và xem kế hoạch mới.')
                    from api.chapters import owned_artifact
                    owned_artifact(repo,db,job.book_id,artifact.id)
        from api.job_conflicts import check_conflicts
        check_conflicts(db,job)
        safe_directory(folder)
        report=folder/'report.json';check_path(report)
        previous=json.loads(report.read_text()) if report.is_file() else {}
        atomic_json(marker,previous)
        if report.is_file():report.unlink()
        job.status='queued';db.add(job)
        return {'id':job.id,'status':job.status}


def attach_routes(router,call):
    @router.post('/{job_id}/stop')
    def stop_job(job_id:UUID,request:Request):return call(request,lambda r:stop(r,job_id))
    @router.post('/{job_id}/resume')
    def resume_job(job_id:UUID,request:Request):return call(request,lambda r:resume(r,job_id))
