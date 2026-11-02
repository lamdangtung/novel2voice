"""T23 persisted translation→TTS stages, with no translator repeat after TTS failure."""
import json
from sqlmodel import select
from api.books import BookError,safe_directory
from api.storage import session_scope
from api.storage.models import Artifact
from api.chapters import owned_artifact
from api.audio_imports import media
from api.configuration import check_path
from api.verification.workspace import atomic_json
from api.web_translation import one as translate_one
from api.web_tts import perform as tts_one,partial_steps
from src.text_chunker import TextChunker


def perform_job(repo,job,verification):
    config=json.loads(job['config_json']);plan=config['plan'];root=safe_directory(repo.root/'job-results'/job['id'])
    policies=plan['policies'];reports=[];completed=0;total=config['steps'];stopped=False
    from api.job_control import stop_requested
    for original in plan['chapters']:
        if stop_requested(repo,job['id']):stopped=True;break
        item=dict(original);folder=safe_directory(root/('chapters/'+item['id'] if len(plan['chapters'])>1 else ''))
        saved_stage=folder/'translation-stage.json';check_path(saved_stage)
        translation_item={**item,'action':item.get('translation_action','create_translation'),'chunk_count':item.get('translation_chunk_count',1)}
        if item.get('translation_artifact_id'):translation_item['reuse_artifact_id']=item['translation_artifact_id']
        if saved_stage.is_file():
            stage=json.loads(saved_stage.read_text())
            if stage.get('status')=='completed':translation_item.update(action='reuse_translation',reuse_artifact_id=stage['artifact_id'])
        translation_item['verification_failure']=item.get('verification_failure',False) and policies.get('verification_fail_stage','tts')=='translate'
        atomic_json(root/'progress.json',{'completed_steps':completed,'total_steps':total,'active_stage':'translate','stage_reused':translation_item['action']=='reuse_translation','active_chapter':item['id']})
        translation_report=None;tts_report=None
        try:
            translation_report=translate_one(repo,job,verification,translation_item)
            if translation_report['status']=='stopped':stopped=True
            if not stopped:
                atomic_json(saved_stage,translation_report)
                completed+=translation_item['chunk_count']
                with session_scope(repo.engine) as db:
                    translated,_,_,content=owned_artifact(repo,db,job['book_id'],translation_report['artifact_id'])
                    if not translated.verified:raise BookError('Bản dịch đã đổi, cần chốt lại đầu vào.')
                    translation_sha=translated.sha256
                vi_chunks=len(TextChunker(max_chars=plan['configuration']['chunk_chars']).chunk_text(content.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')))
                total+=vi_chunks-(item['chunk_count']-translation_item['chunk_count'])
                tts_item={**item,'action':'create_tts','chunk_count':vi_chunks,'tts_input_artifact_id':translation_report['artifact_id'],'tts_input_sha256':translation_sha,
                          'verification_failure':item.get('verification_failure',False) and policies.get('verification_fail_stage','tts')=='tts'}
                if not policies['force'] and policies['resume'] and not tts_item['verification_failure']:
                    with session_scope(repo.engine) as db:
                        for audio in db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='audio',Artifact.verified==True)).all():
                            data=json.loads(audio.provenance)
                            if data.get('tts_fingerprint')==item['tts_fingerprint'] and data.get('translation_sha256')==translation_sha and data.get('source_hash')==item['sha256']:
                                try:media(repo,db,job['book_id'],audio.id)
                                except BookError:continue
                                tts_item.update(action='reuse',reuse_artifact_id=audio.id);break
                atomic_json(root/'progress.json',{'completed_steps':completed,'total_steps':total,'active_stage':'tts','active_chapter':item['id'],'active_output':str(folder/'speech.mp3')})
                if item.get('keep_imported_artifact_id'):
                    with session_scope(repo.engine) as db:audio,_,_=media(repo,db,job['book_id'],item['keep_imported_artifact_id'])
                    tts_report={'status':'completed','artifact_id':audio.id,'provider_calls':0,'reused':True,'notice':'Giữ audio nhập trước theo policy; cần đối chiếu nội dung với bản dịch.'}
                else:tts_report=tts_one(repo,job,verification,tts_item)
                tts_report.update(steps=vi_chunks,completed_steps=vi_chunks if tts_report['status']=='completed' else partial_steps(repo,job,item))
                stopped=tts_report['status']=='stopped'
                completed+=vi_chunks if tts_report['status']=='completed' else partial_steps(repo,job,item)
            status='stopped' if stopped else 'completed'
        except Exception:
            status='failed';bridge=folder/'bridge-report.json';check_path(bridge)
            bridge_report=json.loads(bridge.read_text()) if bridge.is_file() and bridge.stat().st_size<65536 else {'provider_calls':0}
            if translation_report and translation_report.get('status')=='completed':tts_report={**bridge_report,'status':'failed'};completed+=partial_steps(repo,job,item)
            else:translation_report={**bridge_report,'status':'failed','retry_scope':'whole_chapter'}
        report={'status':status,'chapter_id':item['id'],'number':item.get('number'),'translation':translation_report,'tts':tts_report,
                'translation_artifact_id':translation_report.get('artifact_id') if translation_report else translation_item.get('reuse_artifact_id'),
                'artifact_id':tts_report.get('artifact_id') if tts_report else None,'translation_completed':bool(translation_report and translation_report.get('status')=='completed'),
                'provider_calls':sum((r or {}).get('provider_calls',0) for r in [translation_report,tts_report]),
                'translator_calls':(translation_report or {}).get('provider_calls',0),'tts_calls':(tts_report or {}).get('provider_calls',0),
                'notice':'Bản dịch đã giữ riêng; tiếp tục TTS không dịch lại. Nếu bản dịch đổi, cần xem trước lại.' if translation_report and translation_report.get('status')=='completed' else 'Dịch chưa hoàn tất; retry cần dịch lại toàn chương.'}
        if report['translation_artifact_id']:
            with session_scope(repo.engine) as db:report['translation_sha256']=db.get(Artifact,report['translation_artifact_id']).sha256
        reports.append(report);atomic_json(root/'progress.json',{'completed_steps':completed,'total_steps':total,'active_stage':None,'active_chapter':None})
        if stopped or (status=='failed' and not policies['continue_on_error']):break
    if len(reports)==1 and len(plan['chapters'])==1:return {**reports[0],'steps':total,'completed_steps':completed}
    return {'status':'stopped' if stopped else 'failed' if any(r['status']=='failed' for r in reports) else 'completed','chapters':reports,
            'steps':total,'completed_steps':completed,'provider_calls':sum(r['provider_calls'] for r in reports),
            'notice':'Kết quả theo từng bước dịch/TTS; bản dịch đã hoàn thành được giữ riêng.'}
