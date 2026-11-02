"""T20 recovery under the exclusive worker lock; never auto-complete interrupted jobs."""
import json
import os
import signal
import subprocess
import time
from sqlmodel import select
from sqlalchemy import text
from api.configuration import check_path
from api.books import safe_directory
from api.storage import session_scope
from api.storage.models import Job, Artifact, Chapter
from api.audio_imports import media
from api.verification.workspace import atomic_json


def bridge_alive(repo,job_id):
    folder=repo.root/'job-results'/str(job_id)
    candidates=[folder/'bridge-process.json',*folder.glob('chapters/*/bridge-process.json')]
    alive=[]
    for path in candidates:
        check_path(path)
        if not path.is_file() or path.stat().st_size>4096:continue
        try:
            record=json.loads(path.read_text());pid=int(record['pid']);manifest=str(path.with_name('bridge-request.json'))
            command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=2).stdout
            module=record.get('module','src.web_tts_bridge')
            if module in {'src.web_tts_bridge','src.web_translate_bridge','src.web_merge_bridge'} and module in command and manifest in command:alive.append(pid)
        except (ValueError,KeyError,OSError,subprocess.TimeoutExpired):continue
    return alive


def recover(repo):
    with session_scope(repo.engine) as db:
        jobs=[j.model_dump() for j in db.exec(select(Job).where(Job.status.in_(['running','stop_requested']))).all()]
    for job in jobs:
        for pid in bridge_alive(repo,job['id']):
            try:os.kill(pid,signal.SIGUSR1)
            except ProcessLookupError:pass
        deadline=time.monotonic()+3
        while bridge_alive(repo,job['id']) and time.monotonic()<deadline:time.sleep(.1)
        folder=safe_directory(repo.root/'job-results'/job['id']);report_path=folder/'report.json';check_path(report_path)
        previous={}
        if report_path.is_file() and report_path.stat().st_size<65536:
            try:previous=json.loads(report_path.read_text())
            except ValueError:pass
        config=json.loads(job['config_json']);chapters=previous.get('chapters',[])
        if previous.get('chapter_id'):chapters=[previous]
        # Recover already-published chapter results if the worker died between
        # the artifact commit and final job report. No MP3 is inferred by filename.
        if job['kind']=='tts':
            with session_scope(repo.engine) as db:
                expected={i['id']:i for i in config.get('plan',{}).get('chapters',[])}
                for artifact in db.exec(select(Artifact).join(Chapter).where(Artifact.kind=='audio',Chapter.book_id==job['book_id'])).all():
                    data=json.loads(artifact.provenance)
                    if data.get('job_id')!=job['id'] or artifact.chapter_id not in expected:continue
                    if any(c.get('chapter_id')==artifact.chapter_id and c.get('status')=='completed' for c in chapters):continue
                    try:media(repo,db,job['book_id'],artifact.id)
                    except Exception:continue
                    item=expected[artifact.chapter_id]
                    if data.get('source_hash')==item.get('sha256') and data.get('tts_fingerprint')==item.get('tts_fingerprint'):
                        chapters.append({'status':'completed','chapter_id':artifact.chapter_id,'number':item.get('number'),'artifact_id':artifact.id,'provider_calls':0,'reused':True})
        if job['kind']=='process':
            from api.chapters import owned_artifact
            with session_scope(repo.engine) as db:
                for item in config.get('plan',{}).get('chapters',[]):
                    stage_folder=safe_directory(folder/('chapters/'+item['id'] if len(config['plan']['chapters'])>1 else ''))
                    stage_file=stage_folder/'translation-stage.json';check_path(stage_file)
                    if not stage_file.is_file():
                        for artifact in db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='translation_txt')).all():
                            data=json.loads(artifact.provenance)
                            if data.get('job_id')==job['id'] and data.get('translation_fingerprint')==item.get('translation_fingerprint') and data.get('source_hash')==item['sha256']:
                                atomic_json(stage_file,{'status':'completed','artifact_id':artifact.id,'output_sha256':artifact.sha256,'provider_calls':0,'reused':True});break
                    if stage_file.is_file():
                        stage=json.loads(stage_file.read_text());artifact=db.get(Artifact,stage.get('artifact_id'))
                        if artifact and not any(c.get('chapter_id')==item['id'] for c in chapters):
                            chapters.append({'status':'interrupted','chapter_id':item['id'],'translation_completed':True,'translation_artifact_id':artifact.id,'translation_sha256':artifact.sha256})
        completed=0
        total=config.get('steps',0)
        if job['kind']=='process':
            progress_path=folder/'progress.json';check_path(progress_path)
            progress=json.loads(progress_path.read_text()) if progress_path.is_file() and progress_path.stat().st_size<4096 else {}
            completed=progress.get('completed_steps',0);total=progress.get('total_steps',total);active=progress.get('active_chapter')
            item=next((i for i in config['plan']['chapters'] if i['id']==active),None)
            if item and progress.get('active_stage')=='tts':
                from api.web_tts import partial_steps
                completed+=partial_steps(repo,job,item)
            elif item and progress.get('active_stage')=='translate' and not progress.get('stage_reused'):
                log=folder/('chapters/'+active if len(config['plan']['chapters'])>1 else '')/'calls.jsonl';check_path(log)
                events=[]
                if log.is_file() and log.stat().st_size<2*1024*1024:
                    for line in log.read_text().splitlines():
                        try:events.append(json.loads(line))
                        except ValueError:pass
                attempt=max((i for i,e in enumerate(events) if e.get('status')=='attempt'),default=-1)
                completed+=sum(e.get('status')=='completed' and e.get('provider') in {'translator','fake-translator'} for e in events[attempt+1:])
        elif job['kind']=='tts':
            from api.web_tts import partial_steps
            for item in config.get('plan',{}).get('chapters',[]):
                if any(c.get('chapter_id')==item['id'] and c.get('status')=='completed' for c in chapters):completed+=item.get('chunk_count',1)
                else:completed+=partial_steps(repo,job,item)
        else:
            log=folder/'calls.jsonl'
            if log.is_file() and log.stat().st_size<65536:
                for line in log.read_text().splitlines():
                    try:completed+=json.loads(line).get('status')=='completed'
                    except ValueError:pass
        report={'status':'interrupted','steps':total,'completed_steps':completed,'chapters':chapters,
                'notice':'Worker đã dừng đột ngột. Giữ checkpoint và file hợp lệ; tiếp tục sau khi kiểm tra snapshot.',
                'waiting_for_old_bridge':bool(bridge_alive(repo,job['id']))}
        atomic_json(report_path,report)
        with session_scope(repo.engine) as db:
            db.exec(text('BEGIN IMMEDIATE'));row=db.get(Job,job['id'])
            if row.status in {'running','stop_requested'}:row.status='interrupted';db.add(row)
    return len(jobs)
