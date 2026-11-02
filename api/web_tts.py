"""T17 orchestration around the CLI checkpoint runner, with atomic artifact attach."""
import json
import subprocess
import time
import signal
import os
from pathlib import Path
from sqlmodel import select
from sqlalchemy import text
from api.books import BookError, safe_directory
from api.storage import session_scope
from api.storage.models import Chapter, Artifact
from api.chapters import owned_artifact
from api.audio_imports import media, inspect_mp3, digest
from api.configuration import check_path
from api.verification.workspace import PROJECT_ROOT, WorkspaceManager, atomic_json
from src.web_contract import tts_fingerprint


def perform(repo,job,verification,item=None):
    config=json.loads(job['config_json']);plan=config['plan'];item=item or plan['chapters'][0]
    if item['blocked'] or tts_fingerprint(plan['configuration'],verification)!=item['tts_fingerprint']:
        raise BookError('Cấu hình môi trường thay đổi sau xem trước.')
    folder=safe_directory(repo.root/'job-results'/job['id']/(('chapters/'+item['id']) if len(plan['chapters'])>1 else ''))
    with session_scope(repo.engine) as db:
        chapter=db.get(Chapter,item['id'])
        if not chapter or chapter.book_id!=job['book_id'] or chapter.source_hash!=item['sha256'] or chapter.revision!=item['revision']:
            raise BookError('Chương đã đổi sau khi tạo job.')
        input_artifact,_,source,_=owned_artifact(repo,db,job['book_id'],item.get('tts_input_artifact_id',item['source_artifact_id']))
        if item.get('tts_input_artifact_id') and (not input_artifact.verified or input_artifact.sha256!=item.get('tts_input_sha256')):
            raise BookError('Bản dịch đã đổi; cần xem trước lại TTS.')
        if item['action'] in {'reuse','keep_imported'}:
            artifact,_,_=media(repo,db,job['book_id'],item['reuse_artifact_id'])
            if not artifact.verified:raise BookError('Audio đã cần kiểm tra lại sau xem trước.')
            artifact_id=artifact.id
        else:artifact_id=None
    if artifact_id is None:
        output=folder/'speech.mp3';state=safe_directory(repo.root/'books'/job['book_id']/'.tts-cache')
        request={'parent_pid':os.getpid(),'book_root':str(repo.root/'books'/job['book_id']),'input_kind':input_artifact.kind,'source':str(source),'source_hash':item.get('tts_input_sha256',item['sha256']),'output':str(output),'state_dir':str(state),'configuration':plan['configuration'],
                 'fingerprint':item['tts_fingerprint'],'chapter_id':item['id'],'verification_failure':item.get('verification_failure',False),
                 'verification_delay_ms':plan.get('policies',{}).get('verification_delay_ms',0),'verification_fail_on_call':plan.get('policies',{}).get('verification_fail_on_call'),
                 'resume':True if (repo.root/'job-results'/job['id']/'resume-state.json').is_file() else plan.get('policies',{}).get('resume',True),'force':False if (repo.root/'job-results'/job['id']/'resume-state.json').is_file() else plan.get('policies',{}).get('force',False),'verification':verification,'log':str(folder/'calls.jsonl')}
        if verification:
            manager=WorkspaceManager();manager.create('queue-fixture');request['fixture']=str(manager.target('queue-fixture')/'fixtures/tone.mp3')
        manifest=folder/'bridge-request.json';check_path(manifest);atomic_json(manifest,request)
        from api.bridge_runtime import launch
        report=launch(repo,job,folder,'src.web_tts_bridge',manifest)
        if report['status']=='stopped':return report
        duration=inspect_mp3(output)
        if not duration or digest(output)!=report['output_sha256']:raise BookError('Audio chưa qua kiểm tra trước khi công bố.')
    else:report={'provider_calls':0};duration=None
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));chapter=db.get(Chapter,item['id'])
        if chapter.source_hash!=item['sha256'] or chapter.revision!=item['revision']:raise BookError('TXT đã đổi khi TTS đang chạy; không công bố audio vào chương.')
        if item.get('tts_input_artifact_id'):
            translated=db.get(Artifact,item['tts_input_artifact_id'])
            if not translated or not translated.verified or translated.sha256!=item['tts_input_sha256']:raise BookError('Bản dịch đổi khi đang TTS; chưa công bố audio.')
        rows=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='audio')).all()
        for row in rows:
            provenance=json.loads(row.provenance);provenance['selected']=False;row.provenance=json.dumps(provenance);db.add(row)
        if artifact_id:
            selected=db.get(Artifact,artifact_id);data=json.loads(selected.provenance);data['selected']=True;selected.provenance=json.dumps(data);db.add(selected)
        else:
            selected=Artifact(chapter_id=chapter.id,kind='audio',relative_path=output.relative_to(repo.root).as_posix(),sha256=report['output_sha256'],
                              provenance=json.dumps({'method':'generated','selected':True,'source_hash':item['sha256'],'translation_sha256':item.get('tts_input_sha256'),'translation_artifact_id':item.get('tts_input_artifact_id'),'tts_fingerprint':item['tts_fingerprint'],
                                                     'provider_signature':report['provider_signature'],'duration':duration,'verification':verification,'job_id':job['id']}),verified=True)
            db.add(selected);db.flush()
        artifact_id=selected.id
    return {'status':'completed','artifact_id':artifact_id,'provider_calls':report['provider_calls'],'reused':item['action'] in {'reuse','keep_imported'},
            'steps':config['steps'],'completed_steps':config['steps'],'notice':'Tái sử dụng audio; không gọi lại provider.' if item['action'] in {'reuse','keep_imported'} else 'Đã tạo và xác minh audio kiểm thử (âm tone).' if verification else 'Đã tạo và xác minh file audio.'}


def partial_steps(repo,job,item):
    import sqlite3
    state=repo.root/'books'/job['book_id']/'.tts-cache/jobs.sqlite3'
    check_path(state)
    if not state.is_file():return 0
    folder=repo.root/'job-results'/job['id']/('chapters/'+item['id'] if len(json.loads(job['config_json'])['plan']['chapters'])>1 else '')
    db=sqlite3.connect(state.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        row=db.execute('SELECT id FROM jobs WHERE output=? ORDER BY updated_at DESC LIMIT 1',(str(folder/'speech.mp3'),)).fetchone()
        return db.execute("SELECT count(*) FROM chunks WHERE job_id=? AND status='completed'",(row[0],)).fetchone()[0] if row else 0
    except sqlite3.Error:return 0
    finally:db.close()


def perform_job(repo,job,verification):
    config=json.loads(job['config_json']);plan=config['plan'];policies=plan.get('policies',{})
    root=safe_directory(repo.root/'job-results'/job['id']);reports=[];completed=0;stopped=False
    previous={};marker=root/'resume-state.json';check_path(marker)
    if marker.is_file():previous=json.loads(marker.read_text())
    previous_chapters=previous.get('chapters',[])
    if previous.get('chapter_id'):previous_chapters=[previous]
    from api.job_control import stop_requested
    for original_item in plan['chapters']:
        item=dict(original_item)
        if stop_requested(repo,job['id']):stopped=True;break
        prior=next((p for p in previous_chapters if p.get('chapter_id')==item['id'] and p.get('status')=='completed' and p.get('artifact_id')),None)
        if prior:item.update(action='reuse',reuse_artifact_id=prior['artifact_id'])
        subfolder=root/('chapters/'+item['id'] if len(plan['chapters'])>1 else '')
        output=subfolder/'speech.mp3'
        atomic_json(root/'progress.json',{'completed_steps':completed,'active_output':str(output),'active_chapter':item['id']})
        try:
            report=perform(repo,job,verification,item)
            if report['status']=='completed':completed+=item.get('chunk_count',1)
            elif report['status']=='stopped':completed+=partial_steps(repo,job,item);stopped=True
            report.update(chapter_id=item['id'],number=item.get('number'),action=item['action'])
        except Exception:
            bridge=subfolder/'bridge-report.json';calls=0
            check_path(bridge)
            if bridge.is_file() and bridge.stat().st_size<65536:
                try:calls=json.loads(bridge.read_text()).get('provider_calls',0)
                except ValueError:pass
            completed+=partial_steps(repo,job,item)
            report={'steps':config['steps'],'completed_steps':completed,'status':'failed','chapter_id':item['id'],'number':item.get('number'),'provider_calls':calls,
                    'error':'CHAPTER_TTS_FAILED','notice':'Chương lỗi; giữ audio cũ, xem checkpoint để chạy lại.'}
        reports.append(report)
        atomic_json(root/'progress.json',{'completed_steps':completed,'active_output':None,'active_chapter':None})
        if stopped or (report['status']=='failed' and not policies.get('continue_on_error',True)):break
    if len(reports)==1 and len(plan['chapters'])==1:
        final=reports[0]
        if final['status'] in {'completed','stopped'}:final.update(steps=config['steps'],completed_steps=completed)
        return final
    failed=any(r['status']=='failed' for r in reports)
    return {'status':'stopped' if stopped else 'failed' if failed else 'completed','chapters':reports,'provider_calls':sum(r.get('provider_calls',0) for r in reports),
            'processed_chapters':len(reports),'remaining_chapters':len(plan['chapters'])-len(reports),'steps':config['steps'],'completed_steps':completed,
            'notice':'Đã dừng an toàn; có thể tiếp tục từ checkpoint.' if stopped else 'Batch có chương lỗi; các chương đã hoàn thành được giữ nguyên.' if failed else 'Batch hoàn tất; xem kết quả từng chương.'}
