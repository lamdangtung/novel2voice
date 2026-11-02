"""T15 persistent serial queue. Verification action is deliberately opt-in."""
import hashlib
from types import SimpleNamespace
import json
from pathlib import Path
from uuid import UUID, NAMESPACE_OID, uuid5
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import select,func
from api.books import BookError
from api.storage import session_scope
from api.storage.models import Job
from api.configuration import check_path


class TestJobRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    book_id: UUID
    request_id: UUID
    steps: int = Field(default=4,ge=1,le=10)
    delay_ms: int = Field(default=800,ge=0,le=1000)
    fail_on_call: int | None = Field(default=None,ge=1,le=10)


def job_view(job,root,details=False):
    snapshot=json.loads(job.config_json)
    value={'id':job.id,'book_id':job.book_id,'kind':job.kind,'status':job.status,'created_at':job.created_at,
           'steps':snapshot.get('steps',0)}
    if details:
        directory=root/'job-results'/job.id;path=directory/'report.json';check_path(path)
        value['report']=None
        value['snapshot']=snapshot.get('plan')
        if path.is_file() and path.stat().st_size<=65536:value['report']=json.loads(path.read_text())
        if job.status in {'queued','running','stop_requested'}:value['report']=None
        log=directory/'calls.jsonl';check_path(log)
        value['events']=[]
        if log.is_file() and log.stat().st_size<=65536:
            for line in log.read_text().splitlines():
                try:value['events'].append(json.loads(line))
                except ValueError:pass  # Last event may still be flushing while polling.
        value['completed_steps']=sum(e.get('status')=='completed' for e in value['events'])
        if value['report']:
            value['steps']=value['report'].get('steps',value['steps']);value['completed_steps']=value['report'].get('completed_steps',value['completed_steps'])
        if job.kind=='translate':
            progress_path=directory/'progress.json';check_path(progress_path);progress={}
            if progress_path.is_file() and progress_path.stat().st_size<4096:
                try:progress=json.loads(progress_path.read_text())
                except ValueError:pass
            value['completed_steps']=progress.get('completed_steps',0)
            active=progress.get('active_chapter')
            chapters=snapshot.get('plan',{}).get('chapters',[])
            log_dir=directory/('chapters/'+active if active and len(chapters)>1 else '')
            log=log_dir/'calls.jsonl';check_path(log)
            events=[]
            if log.is_file() and log.stat().st_size<=2*1024*1024:
                for line in log.read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
            value['events']=events[-2000:]
            attempt=max((i for i,e in enumerate(events) if e.get('status')=='attempt'),default=-1)
            if active:value['completed_steps']+=sum(e.get('status')=='completed' for e in events[attempt+1:])
            if value['report']:
                value['steps']=value['report'].get('steps',value['steps']);value['completed_steps']=value['report'].get('completed_steps',value['completed_steps'])
        if job.kind=='process':
            progress_path=directory/'progress.json';check_path(progress_path);progress={}
            if progress_path.is_file() and progress_path.stat().st_size<4096:
                try:progress=json.loads(progress_path.read_text())
                except ValueError:pass
            value['completed_steps']=progress.get('completed_steps',0);value['steps']=progress.get('total_steps',value['steps']);value['active_stage']=progress.get('active_stage')
            active=progress.get('active_chapter');chapters=snapshot.get('plan',{}).get('chapters',[])
            log=directory/('chapters/'+active if active and len(chapters)>1 else '')/'calls.jsonl';check_path(log)
            events=[]
            if log.is_file() and log.stat().st_size<=2*1024*1024:
                for line in log.read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
            value['events']=events[-2000:]
            if progress.get('active_stage')=='translate' and not progress.get('stage_reused'):
                attempt=max((i for i,e in enumerate(events) if e.get('status')=='attempt'),default=-1)
                value['completed_steps']+=sum(e.get('status')=='completed' for e in events[attempt+1:] if e.get('provider') in {'translator','fake-translator'})
            elif progress.get('active_stage')=='tts' and active:
                from api.web_tts import partial_steps
                item=next((i for i in chapters if i['id']==active),None)
                if item:value['completed_steps']+=partial_steps(SimpleNamespace(root=root),job.model_dump(),item)
            if value['report']:
                value['completed_steps']=value['report'].get('completed_steps',value['completed_steps']);value['steps']=value['report'].get('steps',value['steps'])
        if job.kind=='tts':
            import sqlite3
            progress_path=directory/'progress.json';check_path(progress_path)
            progress={}
            if progress_path.is_file() and progress_path.stat().st_size<4096:
                try:progress=json.loads(progress_path.read_text())
                except ValueError:pass
            value['completed_steps']=progress.get('completed_steps',value['completed_steps'])
            active=progress.get('active_output',str(directory/'speech.mp3'))
            state=root/'books'/job.book_id/'.tts-cache/jobs.sqlite3';check_path(state)
            if state.is_file() and active:
                connection=sqlite3.connect(state.resolve().as_uri()+'?mode=ro',uri=True,timeout=.2)
                try:
                    row=connection.execute('SELECT id FROM jobs WHERE output=? ORDER BY updated_at DESC LIMIT 1',(active,)).fetchone()
                    if row:
                        counts=connection.execute("SELECT count(*),sum(status='completed') FROM chunks WHERE job_id=?",(row[0],)).fetchone()
                        value['completed_steps']+=counts[1] or 0
                except sqlite3.Error:pass
                finally:connection.close()
            if value['report']:
                value['steps']=value['report'].get('steps',value['steps']);value['completed_steps']=value['report'].get('completed_steps',value['completed_steps'])

    return value


def enqueue_test(repo,body):
    repo.get(body.book_id)
    identifier=str(uuid5(NAMESPACE_OID,'novel2voice:test:'+str(body.request_id)))
    snapshot=json.dumps({'request_id':str(body.request_id),'book_id':str(body.book_id),'steps':body.steps,'delay_ms':body.delay_ms,'fail_on_call':body.fail_on_call},sort_keys=True)
    with session_scope(repo.engine) as db:
        existing=db.get(Job,identifier)
        if existing:
            if existing.config_json!=snapshot:raise BookError('Request ID đã dùng cho một tác vụ khác.')
            return job_view(existing,repo.root)
        job=Job(id=identifier,book_id=str(body.book_id),kind='verification',status='queued',config_json=snapshot)
        db.add(job)
        try:db.flush()
        except IntegrityError:
            db.rollback();existing=db.get(Job,identifier)
            if not existing or existing.config_json!=snapshot:raise BookError('Request ID đang xung đột. Tải lại trước khi thử.')
            return job_view(existing,repo.root)
        return job_view(job,repo.root)


def create_router(settings,provider):
    router=APIRouter(prefix='/api/v1/jobs',tags=['Jobs'])
    def call(request,action):
        try:return action(provider(request))
        except BookError as exc:raise HTTPException(exc.status,str(exc))

    if settings.verification_enabled:
        @router.post('/verification',status_code=201)
        def create_test_job(body:TestJobRequest,request:Request):return call(request,lambda r:enqueue_test(r,body))

    @router.get('')
    def jobs(request:Request,offset:int=Query(default=0,ge=0),limit:int=Query(default=20,ge=1,le=100),book_id:UUID|None=None,status:str='',kind:str=''):
        def action(repo):
            query=select(Job).where(Job.status!='preview')
            if book_id:query=query.where(Job.book_id==str(book_id))
            if status=='attention':query=query.where(Job.status.in_(['failed','stopped','interrupted']))
            elif status:
                if status not in {'queued','running','stop_requested','stopped','interrupted','failed','completed'}:raise BookError('Bộ lọc job không hợp lệ.',422)
                query=query.where(Job.status==status)
            if kind:
                if kind not in {'verification','tts','translate','process','merge','voice_sample'}:raise BookError('Loại job không hợp lệ.',422)
                query=query.where(Job.kind==kind)
            with session_scope(repo.engine) as db:
                total=db.exec(select(func.count()).select_from(query.subquery())).one()
                return {'items':[job_view(j,repo.root) for j in db.exec(query.order_by(Job.created_at.desc(),Job.id).offset(offset).limit(limit)).all()],'total':total,'offset':offset,'limit':limit}
        return call(request,action)

    @router.get('/{job_id}')
    def detail(job_id:UUID,request:Request):
        def action(repo):
            with session_scope(repo.engine) as db:
                job=db.get(Job,str(job_id))
                if job is None:raise BookError('Không tìm thấy tác vụ.',404)
                return job_view(job,repo.root,True)
        return call(request,action)
    from api.retry_plans import attach_routes as attach_retries
    attach_retries(router,call,settings.verification_enabled)
    from api.job_control import attach_routes
    attach_routes(router,call)
    return router
