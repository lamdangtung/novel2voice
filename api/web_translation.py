"""T22 worker orchestration: translation versions published only after full success."""
import json
import os
from sqlmodel import select
from sqlalchemy import text
from api.books import BookError,safe_directory
from api.configuration import check_path
from api.storage import session_scope
from api.storage.models import Chapter,Artifact,Book
from api.chapters import owned_artifact
from api.verification.workspace import atomic_json
from src.translation_contract import identity
from api.bridge_runtime import launch


def one(repo,job,verification,item):
    config=json.loads(job['config_json']);plan=config['plan'];translation=plan['translation'];values=plan['configuration']
    if identity(values,translation['glossary_entries'],verification,translation.get('source_language','en'))['translation_fingerprint']!=item['translation_fingerprint']:
        raise BookError('Model/prompt/endpoint thay đổi sau xem trước.')
    folder=safe_directory(repo.root/'job-results'/job['id']/('chapters/'+item['id'] if len(plan['chapters'])>1 else ''))
    with session_scope(repo.engine) as db:
        if db.get(Book,job['book_id']).language!=translation.get('source_language','en'):raise BookError('Ngôn ngữ gốc đã đổi; cần kế hoạch mới.')
        chapter=db.get(Chapter,item['id'])
        if not chapter or chapter.book_id!=job['book_id'] or chapter.source_hash!=item['sha256'] or chapter.revision!=item['revision']:
            raise BookError('Nguồn đã thay đổi.')
        _,_,source,_=owned_artifact(repo,db,job['book_id'],item['source_artifact_id'])
        if item['action']=='reuse_translation':
            artifact,_,_,_=owned_artifact(repo,db,job['book_id'],item['reuse_artifact_id'])
            if not artifact.verified or json.loads(artifact.provenance).get('translation_fingerprint')!=item['translation_fingerprint']:raise BookError('Bản dịch đã thay đổi sau xem trước.')
            return {'status':'completed','artifact_id':artifact.id,'provider_calls':0,'reused':True,'retry_scope':'whole_chapter',
                    'model':json.loads(artifact.provenance).get('model'),'prompt_hash':json.loads(artifact.provenance).get('prompt_hash'),'glossary_hash':json.loads(artifact.provenance).get('glossary_hash'),
                    'steps':item['chunk_count'],'completed_steps':item['chunk_count'],'notice':'Giữ bản dịch đã xác minh; không gọi translator.'}
    output=folder/'translation.txt'
    request={'parent_pid':os.getpid(),'source':str(source),'source_hash':item['sha256'],'output':str(output),'log':str(folder/'calls.jsonl'),
             'source_language':translation.get('source_language','en'),'configuration':values,'glossary_entries':translation['glossary_entries'],'fingerprint':item['translation_fingerprint'],'verification':verification,
             'chapter_id':item['id'],'verification_failure':item.get('verification_failure',False),
             'verification_fail_on_call':plan['policies'].get('verification_fail_on_call'),'verification_delay_ms':plan['policies'].get('verification_delay_ms',0)}
    manifest=folder/'bridge-request.json';check_path(manifest);atomic_json(manifest,request)
    report=launch(repo,job,folder,'src.web_translate_bridge',manifest)
    if report['status']=='stopped':return report
    check_path(output)
    if not output.is_file() or output.stat().st_size>2*1024*1024:raise BookError('Bản dịch vượt giới hạn hoặc không có file.')
    import hashlib
    content=output.read_bytes()
    if not content.decode('utf-8').strip() or hashlib.sha256(content).hexdigest()!=report['output_sha256']:raise BookError('Bản dịch rỗng hoặc checksum sai.')
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));chapter=db.get(Chapter,item['id'])
        if db.get(Book,job['book_id']).language!=translation.get('source_language','en'):raise BookError('Ngôn ngữ gốc đã đổi khi dịch; chưa công bố bản dịch.')
        if chapter.source_hash!=item['sha256'] or chapter.revision!=item['revision']:raise BookError('Nguồn thay đổi khi đang dịch; không công bố bản dịch.')
        old=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='translation_txt',Artifact.verified==True)).all()
        changed=not old or any(a.sha256!=report['output_sha256'] for a in old)
        for artifact in old:artifact.verified=False;db.add(artifact)
        if changed:
            for audio in db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='audio')).all():audio.verified=False;db.add(audio)
        artifact=Artifact(chapter_id=chapter.id,kind='translation_txt',relative_path=output.relative_to(repo.root).as_posix(),sha256=report['output_sha256'],verified=True,
                          provenance=json.dumps({'method':'translated','source_language':translation.get('source_language','en'),'source_hash':item['sha256'],'model':report['model'],'prompt_hash':report['prompt_hash'],
                                                 'glossary_hash':report['glossary_hash'],'glossary_source_sha256':translation['glossary_source_sha256'],
                                                 'translation_fingerprint':item['translation_fingerprint'],'verification':verification,'job_id':job['id']}))
        db.add(artifact);db.flush();identifier=artifact.id
    return {**report,'artifact_id':identifier,'reused':False}


def perform_job(repo,job,verification):
    config=json.loads(job['config_json']);plan=config['plan'];root=safe_directory(repo.root/'job-results'/job['id'])
    from api.job_control import stop_requested
    reports=[];completed=0;stopped=False
    marker=root/'resume-state.json';check_path(marker);previous=json.loads(marker.read_text()) if marker.is_file() else {}
    old=previous.get('chapters') or ([previous] if previous.get('chapter_id') else [])
    for original in plan['chapters']:
        if stop_requested(repo,job['id']):stopped=True;break
        item=dict(original);prior=next((r for r in old if r.get('chapter_id')==item['id'] and r.get('status')=='completed'),None)
        if prior:item.update(action='reuse_translation',reuse_artifact_id=prior['artifact_id'])
        folder=root/('chapters/'+item['id'] if len(plan['chapters'])>1 else '')
        atomic_json(root/'progress.json',{'completed_steps':completed,'active_chapter':item['id']})
        try:report=one(repo,job,verification,item)
        except Exception:
            bridge=folder/'bridge-report.json';check_path(bridge);report={}
            if bridge.is_file() and bridge.stat().st_size<65536:
                try:report=json.loads(bridge.read_text())
                except ValueError:pass
            report={**report,'status':'failed','error':'TRANSLATION_FAILED','retry_scope':'whole_chapter',
                    'notice':'Dịch lỗi: chưa thay bản đang có. Retry sẽ dịch lại toàn chương và có thể phát sinh lại chi phí.'}
        report.update(chapter_id=item['id'],number=item.get('number'))
        completed+=report.get('completed_steps',0)
        reports.append(report);stopped=report['status']=='stopped'
        atomic_json(root/'progress.json',{'completed_steps':completed,'active_chapter':None})
        if stopped or (report['status']=='failed' and not plan['policies']['continue_on_error']):break
    if len(reports)==1 and len(plan['chapters'])==1:return reports[0]
    return {'status':'stopped' if stopped else 'failed' if any(r['status']=='failed' for r in reports) else 'completed','chapters':reports,
            'steps':config['steps'],'completed_steps':completed,'provider_calls':sum(r.get('provider_calls',0) for r in reports),'retry_scope':'whole_chapter',
            'notice':'Dịch theo chương; chương chưa hoàn tất phải dịch lại toàn chương khi retry, không resume từng đoạn.'}
