"""T16 immutable preview: config captured once, chapter freshness checked at confirm."""
import hashlib
import json
from uuid import UUID, uuid5, NAMESPACE_OID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import select
from api.books import BookError
from api.configuration import read as read_configuration
from api.chapters import detail as chapter_detail
from api.storage import session_scope
from api.storage.models import Job, Chapter, Book


class Policies(BaseModel):
    model_config=ConfigDict(extra='forbid')
    verification_merge_failure: bool=False
    force: bool=False
    resume: bool=True
    keep_imported: bool=True
    continue_on_error: bool=True
    cleanup: bool | None=None
    retries: int | None=Field(default=None,ge=0,le=5)
    verification_fail_stage: str=Field(default='tts',pattern='^(tts|translate)$')
    verification_fail_on_call: int | None=Field(default=None,ge=1,le=100)
    verification_delay_ms: int=Field(default=0,ge=0,le=1000)
    verification_fail_chapters: list[UUID]=Field(default_factory=list,max_length=20)


class PlanRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    book_id: UUID
    chapter_ids: list[UUID]=Field(min_length=1,max_length=20)
    request_id: UUID
    action: str='verification'
    policies: Policies=Field(default_factory=Policies)


def result(job):
    return {'id':job.id,'status':job.status,'plan':json.loads(job.config_json)['plan']}


def preview(repo,body,verification):
    if body.action not in {'verification','tts','translate','process','merge'} or (body.action=='verification' and not verification):raise BookError('Action này chưa khả dụng; chưa tạo tác vụ.',422)
    if (body.policies.verification_fail_chapters or body.policies.verification_delay_ms or body.policies.verification_fail_on_call or body.policies.verification_merge_failure) and not verification:raise BookError('Lỗi chủ động chỉ dùng trong chế độ kiểm thử.',422)
    if not set(body.policies.verification_fail_chapters).issubset(body.chapter_ids):raise BookError('Chương gây lỗi phải nằm trong phạm vi đã chọn.',422)
    if len(set(body.chapter_ids))!=len(body.chapter_ids):raise BookError('Danh sách chương bị trùng.',422)
    identifier=str(uuid5(NAMESPACE_OID,'novel2voice:plan:'+str(body.request_id)))
    fingerprint=hashlib.sha256(json.dumps([str(body.book_id),body.action,sorted(str(x) for x in body.chapter_ids),body.policies.model_dump(mode='json')]).encode()).hexdigest()
    with session_scope(repo.engine) as db:
        existing=db.get(Job,identifier)
        if existing:
            if json.loads(existing.config_json).get('request_fingerprint')!=fingerprint:raise BookError('Request ID đã dùng cho kế hoạch khác.')
            return result(existing)
    book=repo.get(body.book_id);configuration=read_configuration(repo,body.book_id)['effective'] if body.action!='merge' else {};items=[]
    if body.policies.cleanup is not None:configuration['cleanup']=body.policies.cleanup
    if body.policies.retries is not None:configuration['retries']=body.policies.retries
    for chapter_id in body.chapter_ids:
        try:
            if body.action=='merge':
                with session_scope(repo.engine) as db:
                    chapter=db.get(Chapter,str(chapter_id))
                    if chapter is None or chapter.book_id!=str(body.book_id):raise BookError('Không tìm thấy chương.',404)
                    items.append({'id':chapter.id,'number':chapter.number,'revision':chapter.revision,'sha256':chapter.source_hash,'blocked':False,'chunk_count':1})
                continue
            detail=chapter_detail(repo,body.book_id,chapter_id,include_translation=False)
            if detail['source'] is None:raise BookError('Thiếu văn bản gốc.')
            items.append({'id':str(chapter_id),'number':detail['number'],'revision':detail['revision'],'sha256':detail['source']['sha256'],'action':'create_test',
                          'message':'Tạo đoạn kiểm thử riêng; giữ nguyên audio hiện có.','blocked':False})
        except BookError as exc:
            items.append({'id':str(chapter_id),'blocked':True,'message':str(exc)})
    if body.action=='tts':
        from src.web_contract import tts_fingerprint
        from src.text_chunker import TextChunker
        from api.storage.models import Artifact
        from api.audio_imports import media
        from api.verification.workspace import PROJECT_ROOT
        import shutil
        runtime_fingerprint=tts_fingerprint(configuration,verification)
        for item in items:
            if item['blocked']:continue
            if not verification and configuration['provider']=='openai':
                from src.doctor import read_config
                if not (read_config().get('OPENAI_API_KEY') or '').strip():
                    item.update(blocked=True,message='Chưa cấu hình OPENAI_API_KEY trên server; chưa gọi dịch vụ.');continue
            if book.language!='vi':
                item.update(blocked=True,message='Nguồn chưa phải tiếng Việt. Chọn dịch rồi TTS để tạo giọng VI.');continue
            if not (PROJECT_ROOT/'.venv/bin/python').is_file() or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
                item.update(blocked=True,message='Thiếu Python CLI hoặc FFmpeg/ffprobe. Mở Môi trường để kiểm tra.');continue
            source=chapter_detail(repo,body.book_id,item['id'],include_translation=False)['source']
            item['source_artifact_id']=source['artifact_id'];item['chunk_count']=len(TextChunker(max_chars=configuration['chunk_chars']).chunk_text(source['text'].replace('\r\n','\n').replace('\r','\n')))
            item['action']='create_tts';item['message']='Tạo audio từ văn bản VI bằng provider kiểm thử.' if verification else 'Tạo giọng thật; có thể tải model/gọi mạng và phát sinh chi phí theo provider.'
            item['tts_fingerprint']=runtime_fingerprint
            with session_scope(repo.engine) as db:
                audios=db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='audio',Artifact.verified==True)).all()
                audios.sort(key=lambda a:0 if json.loads(a.provenance).get('method')=='imported' and json.loads(a.provenance).get('selected') else 1)
                for audio in audios:
                    provenance=json.loads(audio.provenance)
                    keep_imported=body.policies.keep_imported and provenance.get('method')=='imported' and provenance.get('selected') and provenance.get('source_hash')==item['sha256']
                    reusable=not body.policies.force and body.policies.resume and provenance.get('tts_fingerprint')==runtime_fingerprint and provenance.get('source_hash')==item['sha256']
                    if keep_imported or reusable:
                        try:media(repo,db,body.book_id,audio.id)
                        except BookError:continue
                        item.update(action='keep_imported' if keep_imported else 'reuse',reuse_artifact_id=audio.id,
                                    message='Giữ MP3 nhập trước (kể cả force); chưa xác minh khớp từng từ.' if keep_imported else 'Tái sử dụng audio đã xác minh cùng nội dung/giọng/cấu hình.');break
            if item['id'] in [str(x) for x in body.policies.verification_fail_chapters]:
                item.update(action='create_tts',verification_failure=True,message='Lỗi chủ động tại chương này; không dùng cache để đảm bảo thử retry.')
    translation=None
    if body.action in {'translate','process'}:
        from api.glossaries import read as read_glossary
        from src.translation_contract import identity
        from api.storage.models import Artifact
        from api.chapters import owned_artifact
        from src.text_chunker import TextChunker
        glossary=read_glossary(repo,body.book_id);ident=identity(configuration,glossary['entries'],verification,book.language)
        translation={'source_language':book.language,**ident,'glossary_entries':glossary['entries'],'glossary_source_sha256':glossary['sha256'],'model':configuration['translation_model']}
        for item in items:
            if item['blocked']:continue
            if book.language=='vi':item.update(blocked=True,message='Truyện đã là tiếng Việt; chọn TTS trực tiếp.');continue
            if not verification:
                from src.doctor import read_config
                if not (read_config().get('OPENAI_API_KEY') or '').strip():
                    item.update(blocked=True,message='Thiếu OPENAI_API_KEY trên server; chưa gọi dịch vụ.');continue
            source=chapter_detail(repo,body.book_id,item['id'],include_translation=False)['source']
            item.update(source_artifact_id=source['artifact_id'],chunk_count=len(TextChunker(max_chars=configuration['chunk_chars']).chunk_text(source['text'].replace('\r\n','\n').replace('\r','\n'))),
                        translation_fingerprint=ident['translation_fingerprint'],action='create_translation',message='Dịch toàn chương; nếu lỗi/stop, retry sẽ dịch lại toàn chương.')
            with session_scope(repo.engine) as db:
                existing=db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='translation_txt',Artifact.verified==True).order_by(Artifact.created_at.desc())).first()
                if existing:
                    try:owned_artifact(repo,db,body.book_id,existing.id)
                    except Exception:existing=None
                if existing:
                    provenance=json.loads(existing.provenance)
                    if provenance.get('translation_fingerprint')==ident['translation_fingerprint'] and not body.policies.force:
                        item.update(action='reuse_translation',reuse_artifact_id=existing.id,message='Giữ bản dịch đã xác minh cùng nguồn/model/prompt/glossary.')
                    elif not body.policies.force:item.update(blocked=True,message='Đã có bản dịch khác. Cần chọn xác nhận tạo bản dịch mới; bản cũ sẽ giữ riêng.')
            if item['id'] in [str(x) for x in body.policies.verification_fail_chapters]:
                item.update(action='create_translation',verification_failure=True,message='Lỗi translator chủ động; chưa công bố bản dịch dở.')
    if body.action=='process':
        from src.web_contract import tts_fingerprint
        from api.storage.models import Artifact
        from api.audio_imports import media
        for item in items:
            if item['blocked']:continue
            item['translation_action']=item['action'];item['translation_chunk_count']=item['chunk_count']
            item['tts_fingerprint']=tts_fingerprint(configuration,verification)
            if item.get('reuse_artifact_id'):
                item['translation_artifact_id']=item.pop('reuse_artifact_id')
                with session_scope(repo.engine) as db:item['translation_expected_sha']=db.get(Artifact,item['translation_artifact_id']).sha256
            item['action']='process';item['message']='Dịch hoặc giữ bản dịch đã xác minh, sau đó tạo audio VI. Tiếp tục dùng đúng bản dịch đã lưu.'
            item['chunk_count']*=2
            if body.policies.keep_imported:
                with session_scope(repo.engine) as db:
                    for audio in db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='audio')).all():
                        provenance=json.loads(audio.provenance)
                        if provenance.get('method')=='imported' and provenance.get('selected'):
                            try:media(repo,db,body.book_id,audio.id)
                            except Exception:continue
                            item['keep_imported_artifact_id']=audio.id
                            item['message']+=' Giữ audio nhập trước theo policy; cần đối chiếu với bản dịch.';break
    merge=None
    if body.action=='merge':
        import math
        from api.storage.models import Artifact,BookArtifact
        from api.audio_imports import media,inspect_mp3
        from api.merged_audio import media as merged_media
        items.sort(key=lambda i:(i.get('number',0),i['id']));total_bytes=0
        for item in items:
            if item['blocked']:continue
            if total_bytes>512*1024*1024:item.update(blocked=True,message='Tổng audio ghép vượt512MiB.');continue
            with session_scope(repo.engine) as db:
                selected=[a for a in db.exec(select(Artifact).where(Artifact.chapter_id==item['id'],Artifact.kind=='audio')).all() if json.loads(a.provenance).get('selected')]
                if len(selected)!=1:item.update(blocked=True,message='Chương thiếu audio đang chọn.');continue
                audio=selected[0];data=json.loads(audio.provenance)
                if not audio.verified or data.get('source_hash')!=item['sha256']:item.update(blocked=True,message='Audio cũ/cần kiểm tra lại; giải quyết trước khi ghép.');continue
                try:_,_,path=media(repo,db,body.book_id,audio.id)
                except Exception:item.update(blocked=True,message='Audio mất/hỏng/checksum sai.');continue
                total_bytes+=path.stat().st_size
                if total_bytes>512*1024*1024:item.update(blocked=True,message='Tổng audio ghép vượt512MiB.');continue
                duration=data.get('duration') or inspect_mp3(path)
                if not duration or not math.isfinite(duration):item.update(blocked=True,message='Không xác định được thời lượng audio.');continue
                item.update(action='merge_input',audio_id=audio.id,audio_sha256=audio.sha256,duration=duration,message='Giữ nguyên file chương, dùng audio đã chọn trong snapshot.')
        manifest=[{'chapter_id':i['id'],'number':i.get('number'),'artifact_id':i.get('audio_id'),'sha256':i.get('audio_sha256')} for i in items]
        signature=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        merge={'source_signature':signature,'manifest':manifest,'input_duration':sum(i.get('duration',0) for i in items),'bytes':total_bytes,'reuse_artifact_id':None}
        if not body.policies.force and not body.policies.verification_merge_failure and not any(i['blocked'] for i in items):
            with session_scope(repo.engine) as db:
                for artifact in db.exec(select(BookArtifact).where(BookArtifact.book_id==str(body.book_id),BookArtifact.source_signature==signature).order_by(BookArtifact.created_at.desc())).all():
                    try:merged_media(repo,db,body.book_id,artifact.id)
                    except Exception:continue
                    merge['reuse_artifact_id']=artifact.id;break
    plan={'source_language':book.language,'merge':merge,'translation':translation,'policies':body.policies.model_dump(mode='json'),'action':body.action,'execution_provider':'ffmpeg' if body.action=='merge' else ('fake-translator' if verification else 'openai-compatible') if body.action=='translate' else ('fake-translator + fake-tts' if verification else 'translator + TTS') if body.action=='process' else 'fake-tts' if verification else configuration['provider'],'configuration':configuration,'chapters':items,
          'notice':'Ghép file hiện có bằng FFmpeg, không gọi TTS. Snapshot thứ tự/audio được giữ cố định.' if body.action=='merge' else 'Snapshot cấu hình được giữ cố định sau xem trước. '+('Không gọi provider thật.' if verification else 'Provider thật có thể dùng mạng/tải model/chi phí. Xác nhận để chạy.')}
    config=json.dumps({'request_fingerprint':fingerprint,'plan':plan,'steps':sum(x.get('chunk_count',1) for x in items),'delay_ms':800,'fail_on_call':None},sort_keys=True)
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));existing=db.get(Job,identifier)
        if existing:
            if json.loads(existing.config_json).get('request_fingerprint')!=fingerprint:raise BookError('Request ID xung đột.')
            return result(existing)
        job=Job(id=identifier,book_id=str(body.book_id),kind=body.action,status='preview',config_json=config);db.add(job);db.flush()
        return result(job)


def confirm(repo,plan_id):
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));job=db.get(Job,str(plan_id))
        if job is None:raise BookError('Không tìm thấy kế hoạch.',404)
        config=json.loads(job.config_json)
        if 'plan' not in config:raise BookError('Không tìm thấy kế hoạch.',404)
        if job.status!='preview':return result(job)
        if config['plan'].get('source_language') and db.get(Book,job.book_id).language!=config['plan']['source_language']:raise BookError('Ngôn ngữ gốc đã đổi sau xem trước. Cần tạo kế hoạch mới.')
        if config['plan'].get('blocked'):raise BookError('Chưa đủ điều kiện: '+'; '.join(config['plan'].get('blocked_reasons',[])))
        for item in config['plan']['chapters']:
            chapter=db.get(Chapter,item['id'])
            if item['blocked'] or not chapter or chapter.book_id!=job.book_id or chapter.revision!=item['revision'] or chapter.source_hash!=item['sha256']:
                raise BookError('Chương bị chặn hoặc đã thay đổi sau xem trước. Xem trước lại.')
            translated_id=item.get('translation_artifact_id') or item.get('tts_input_artifact_id')
            expected_translation=item.get('translation_expected_sha') or item.get('tts_input_sha256')
            if translated_id and expected_translation:
                from api.storage.models import Artifact
                from api.chapters import owned_artifact
                artifact=db.get(Artifact,translated_id)
                if not artifact or not artifact.verified or artifact.sha256!=expected_translation:
                    raise BookError('Bản dịch đã thay đổi sau xem trước; cần đối chiếu và chốt lại đầu vào.')
                owned_artifact(repo,db,job.book_id,translated_id)
            if config['plan']['action']=='merge':
                from api.audio_imports import media
                audio,_,_=media(repo,db,job.book_id,item['audio_id'])
                if not audio.verified or audio.sha256!=item['audio_sha256'] or not json.loads(audio.provenance).get('selected'):
                    raise BookError('Audio đã đổi sau xem trước; cần xem kế hoạch mới.')
                continue
            current=chapter_detail(repo,job.book_id,chapter.id,include_translation=False)
            if current['source'] is None or current['source']['sha256']!=item['sha256']:raise BookError('Nội dung nguồn đã thay đổi. Xem trước lại.')
        from api.job_conflicts import check_conflicts
        check_conflicts(db,job)
        job.status='queued';db.add(job)
        return result(job)


def create_router(settings,provider):
    router=APIRouter(prefix='/api/v1/job-plans',tags=['Job plans'])
    def call(request,action):
        try:return action(provider(request))
        except BookError as exc:raise HTTPException(exc.status,str(exc))
    @router.post('',status_code=201)
    def create_plan(body:PlanRequest,request:Request):return call(request,lambda r:preview(r,body,settings.verification_enabled))
    @router.post('/{plan_id}/confirm')
    def confirm_plan(plan_id:UUID,request:Request):return call(request,lambda r:confirm(r,plan_id))
    return router
