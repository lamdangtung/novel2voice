"""T21 scoped retry plans, sharing validated core cache but preserving prior reports."""
import hashlib
import json
from uuid import UUID, uuid5, NAMESPACE_OID
from pydantic import BaseModel,ConfigDict
from fastapi import Request
from sqlalchemy import text
from api.books import BookError
from api.storage import session_scope
from api.storage.models import Job,Chapter,Artifact
from api.configuration import check_path
from api.audio_imports import media
from api.chapters import owned_artifact
from api.job_plans import result
from src.web_contract import tts_fingerprint


class RetryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    clear_verification_faults: bool=False


def preview_retry(repo,job_id,body,verification):
    if body.clear_verification_faults and not verification:raise BookError('Chỉ bỏ lỗi giả lập trong chế độ kiểm thử.',422)
    identifier=str(uuid5(NAMESPACE_OID,'novel2voice:retry:'+str(body.request_id)))
    fingerprint=hashlib.sha256(json.dumps([str(job_id),body.model_dump(mode='json')],sort_keys=True).encode()).hexdigest()
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'))
        existing=db.get(Job,identifier)
        if existing:
            if json.loads(existing.config_json).get('request_fingerprint')!=fingerprint:raise BookError('Request ID đã dùng cho retry khác.')
            return result(existing)
        original=db.get(Job,str(job_id))
        if not original or original.kind not in {'tts','translate','process'}:raise BookError('Không tìm thấy job TTS.',404)
        if original.status not in {'failed','completed'}:raise BookError('Job đang chạy/đã dừng cần hoàn tất hoặc tiếp tục trước.')
        config=json.loads(original.config_json);plan=config['plan'];path=repo.root/'job-results'/original.id/'report.json';check_path(path)
        if not path.is_file() or path.stat().st_size>65536:raise BookError('Thiếu báo cáo để xác định phạm vi retry.')
        report=json.loads(path.read_text());reports=report.get('chapters') or ([report] if report.get('chapter_id') else [])
        scope=[];invalid=[]
        for original_item in plan['chapters']:
            row=next((r for r in reports if r.get('chapter_id')==original_item['id']),None)
            needs_retry=row is None or row.get('status')!='completed'
            if row and row.get('status')=='completed' and row.get('artifact_id'):
                try:
                    if original.kind=='translate':owned_artifact(repo,db,original.book_id,row['artifact_id'])
                    else:media(repo,db,original.book_id,row['artifact_id'])
                except BookError:
                    needs_retry=True;invalid.append(row['artifact_id'])
            if not needs_retry:continue
            item=dict(original_item);chapter=db.get(Chapter,item['id'])
            if not chapter or chapter.source_hash!=item.get('sha256') or chapter.revision!=item.get('revision'):
                raise BookError('Nguồn đã đổi; tạo kế hoạch mới thay vì retry snapshot cũ.')
            owned_artifact(repo,db,original.book_id,item['source_artifact_id'])
            if original.kind in {'translate','process'}:
                from src.translation_contract import identity
                runtime_matches=identity(plan['configuration'],plan['translation']['glossary_entries'],verification,plan['translation'].get('source_language','en'))['translation_fingerprint']==item.get('translation_fingerprint')
            else:runtime_matches=tts_fingerprint(plan['configuration'],verification)==item.get('tts_fingerprint')
            if original.kind=='process':runtime_matches=runtime_matches and tts_fingerprint(plan['configuration'],verification)==item.get('tts_fingerprint')
            if not runtime_matches:
                raise BookError('Cấu hình server đã đổi; cần xem trước kế hoạch mới.')
            item.update(action='process' if original.kind=='process' else 'create_translation' if original.kind=='translate' else 'create_tts',message='Dịch lại toàn chương lỗi; không resume từng đoạn.' if original.kind=='translate' else 'Retry phạm vi lỗi; tái dùng các đoạn còn hash/audio hợp lệ.')
            if original.kind=='process' and row and row.get('translation_artifact_id'):
                translated,_,_,_=owned_artifact(repo,db,original.book_id,row['translation_artifact_id'])
                if not translated.verified or translated.sha256!=row.get('translation_sha256'):
                    raise BookError('Bản dịch đã đổi sau lỗi TTS; cần đối chiếu và xem kế hoạch mới.')
                item.update(translation_action='reuse_translation',translation_artifact_id=translated.id,translation_expected_sha=translated.sha256,message='Giữ bản dịch đã chốt; chỉ tiếp tục bước TTS còn thiếu, không gọi translator lại.')
            item.pop('reuse_artifact_id',None)
            if body.clear_verification_faults:item.pop('verification_failure',None)
            scope.append(item)
        if not scope:raise BookError('Không có chương lỗi/audio hỏng cần retry. Dùng force trong kế hoạch mới nếu muốn tạo lại.')
        plan={**plan,'chapters':scope,'retry_of':original.id,'policies':{**plan.get('policies',{}),'force':False,'resume':True},
              'notice':('Dịch lại toàn chương chưa hoàn tất; có thể phát sinh lại chi phí. ' if original.kind=='translate' else '')+'Retry từ job '+original.id[:8]+': giữ snapshot giọng/nội dung; bỏ qua chương đã thành công và cache hợp lệ.'}
        if body.clear_verification_faults:plan['policies']['verification_fail_chapters']=[]
        config={**config,'plan':plan,'request_fingerprint':fingerprint,'steps':sum(i.get('chunk_count',1) for i in scope),'retry_of':original.id}
        for artifact_id in invalid:
            artifact=db.get(Artifact,artifact_id)
            if artifact:artifact.verified=False;db.add(artifact)
        retry=Job(id=identifier,book_id=original.book_id,kind=original.kind,status='preview',config_json=json.dumps(config,sort_keys=True))
        db.add(retry);db.flush();return result(retry)


def attach_routes(router,call,verification):
    @router.post('/{job_id}/retry-plan',status_code=201)
    def retry_plan(job_id:UUID,body:RetryRequest,request:Request):
        return call(request,lambda r:preview_retry(r,job_id,body,verification))
