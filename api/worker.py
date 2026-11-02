"""One local worker process per library, independent from API lifecycle."""
import argparse
import fcntl
import json
import signal
import threading
import time
from pathlib import Path
from sqlalchemy import text
from sqlmodel import select
from api.books import BookRepository, safe_directory
from api.storage import session_scope
from api.storage.models import Job
from api.configuration import check_path
from api.verification.workspace import PROJECT_ROOT, atomic_json, WorkspaceManager


def claim(repo):
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'))
        job=db.exec(select(Job).where(Job.status=='queued').order_by(Job.created_at,Job.id)).first()
        if job is None:return None
        job.status='running';db.add(job);db.flush()
        return job.model_dump()


def execute(repo,job,verification):
    folder=safe_directory(repo.root/'job-results'/job['id'])
    try:
        if job['kind'] in {'tts','translate','process','merge','voice_sample'}:
            if job['kind']=='voice_sample':
                from api.web_voice import perform_job
            elif job['kind']=='merge':
                from api.web_merge import perform_job
            elif job['kind']=='process':
                from api.web_process import perform_job
            elif job['kind']=='translate':
                from api.web_translation import perform_job
            else:
                from api.web_tts import perform_job
            result=perform_job(repo,job,verification)
            atomic_json(folder/'report.json',result)
            with session_scope(repo.engine) as db:
                row=db.get(Job,job['id']);row.status=result['status'];db.add(row)
            return
        if not verification or job['kind']!='verification':raise ValueError('Unsupported job kind')
        from api.verification.providers import FakeTTSProvider, FaultPlan
        manager=WorkspaceManager();manager.create('queue-fixture');fixture=manager.target('queue-fixture')/'fixtures/tone.mp3'
        config=json.loads(job['config_json'])
        provider=FakeTTSProvider(fixture,folder,folder/'calls.jsonl',FaultPlan(delay_ms=config['delay_ms'],fail_on_calls=(config['fail_on_call'],) if config['fail_on_call'] else ()),chapter_id='queue-test')
        from api.job_control import stop_requested
        import hashlib
        fixture_hash=hashlib.sha256(fixture.read_bytes()).hexdigest();completed=0;stopped=False
        for index in range(config['steps']):
            if stop_requested(repo,job['id']):stopped=True;break
            output=folder/f'step-{index+1}.mp3'
            if output.is_file() and not output.is_symlink() and hashlib.sha256(output.read_bytes()).hexdigest()==fixture_hash:
                completed+=1;continue
            chapters=config.get('plan',{}).get('chapters',[])
            chapter_id=chapters[index]['id'] if chapters else 'queue-test'
            provider.generate_speech('Đoạn kiểm thử '+str(index+1),output,chapter_id=chapter_id,chunk_index=index+1)
            completed+=1
        result={'status':'stopped' if stopped else 'completed','steps':config['steps'],'completed_steps':completed,'fixture':'offline-tone',
                'notice':'Đã dừng an toàn; giữ các bước hợp lệ.' if stopped else 'Job kiểm thử; không phải giọng đọc thật.'}
    except Exception:
        result={'status':'failed','error':'JOB_EXECUTION_FAILED','notice':'Tác vụ thất bại. Kiểm tra môi trường/nội dung; kết quả chưa được công bố vào chương.'}
    if job['kind']=='merge' and result['status']=='failed':result.update(provider_calls=0,notice='Ghép lỗi; nguồn và bản ghép trước giữ nguyên, không gọi TTS.')
    atomic_json(folder/'report.json',result)
    with session_scope(repo.engine) as db:
        row=db.get(Job,job['id']);row.status=result['status'];db.add(row)


def _run(root,verification,stop=None):
    repo=BookRepository(root);stop=stop or threading.Event()
    lock=repo.root/'worker.lock';check_path(lock)
    try:
        with lock.open('a') as stream:
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Đã có worker cho thư viện này.')
            from api.recovery import recover
            recover(repo)
            def heartbeat():
                while not stop.is_set():
                    atomic_json(repo.root/'worker-heartbeat.json',{'updated_at':time.time()})
                    stop.wait(1)
            thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
            try:
                while not stop.is_set():
                    job=claim(repo)
                    if job:execute(repo,job,verification)
                    else:stop.wait(.25)
            finally:
                stop.set();thread.join(timeout=2)
                (repo.root/'worker-heartbeat.json').unlink(missing_ok=True)
    finally:repo.engine.dispose()


def run(root,verification,stop=None):
    from api.maintenance import gate
    with gate(root):return _run(root,verification,stop)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verification',action='store_true');parser.add_argument('--data-dir',type=Path);args=parser.parse_args()
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    root=args.data_dir.resolve() if args.data_dir else PROJECT_ROOT/('.verification/web' if args.verification else '.novel2voice')
    try:run(root,args.verification,stop)
    except RuntimeError as exc:
        print(str(exc),flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
