"""T25 offline voice metadata and book-scoped samples, never chapter artifacts."""
import hashlib
import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import UUID,uuid5,NAMESPACE_OID
from fastapi import Request,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import text
from sqlmodel import select
from api.books import BookError
from api.configuration import read as configuration,Values
from api.storage import session_scope
from api.storage.models import Job,BookArtifact
from api.merged_audio import media as book_media
from api.job_plans import result
from api.verification.workspace import PROJECT_ROOT
from src.doctor import read_config,check_environment
from src.web_contract import tts_fingerprint
from src.text_chunker import TextChunker

Provider=Literal['vieneu','edge-tts','openai','piper']


def catalog(provider):
    if provider=='vieneu':
        mode=read_config().get('VIENEU_MODE') or 'v3turbo'
        if mode=='remote':return {'provider':provider,'default_voice':'','voices':[{'id':'','label':'Mặc định server remote'}],'source':'Không truy vấn server remote khi mở form','runtime_verified':False}
        data=json.loads(Path(__file__).with_name('voice_catalog.json').read_text()).get(mode)
        if not data:raise BookError('Mode VieNeu chưa có catalog offline; kiểm tra cấu hình server.',422)
        return {'provider':provider,**data,'notice':'Metadata giọng đi kèm SDK; chưa nạp model/xác minh giọng, model tùy chỉnh có thể khác.'}
    if provider=='edge-tts':
        return {'provider':provider,'default_voice':'vi-VN-HoaiMyNeural','voices':[{'id':'vi-VN-HoaiMyNeural','label':'Hoài My · Nữ'},{'id':'vi-VN-NamMinhNeural','label':'Nam Minh · Nam'}],
                'source':'Danh sách mặc định CLI v1.0, chưa truy vấn Edge service','runtime_verified':False}
    if provider=='openai':return {'provider':provider,'default_voice':'alloy','voices':[{'id':'alloy','label':'alloy'}],'source':'Giọng mặc định OpenAITTSProvider CLI, model tts-1; không coi là catalog đầy đủ','runtime_verified':False}
    return {'provider':provider,'default_voice':'','voices':[{'id':'','label':'Giọng từ model Piper trên server'}],'source':'Piper dùng file model đã cấu hình; không có voice selector','runtime_verified':False}


class VoiceRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    provider: Provider
    voice: str=Field(default='',max_length=100)
    text: str=Field(min_length=1,max_length=300)
    force: bool=False
    @field_validator('text')
    @classmethod
    def valid_text(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('Câu thử phải có nội dung.')
        return value.strip()


def preview(repo,book_id,body,verification):
    values=configuration(repo,book_id)['effective'];values=Values(**{**values,'provider':body.provider,'voice':body.voice}).model_dump()
    metadata=catalog(body.provider)
    if body.voice not in {v['id'] for v in metadata['voices']}:raise BookError('Giọng không hợp lệ hoặc chưa có trong catalog offline của provider.',422)
    identifier=str(uuid5(NAMESPACE_OID,'novel2voice:voice:'+str(body.request_id)))
    request_hash=hashlib.sha256(json.dumps([str(book_id),body.model_dump(mode='json')],sort_keys=True).encode()).hexdigest()
    fingerprint=tts_fingerprint(values,verification);signature=hashlib.sha256(json.dumps([body.text,fingerprint]).encode()).hexdigest()
    blocked=[]
    if not verification:
        doctor=check_environment(body.provider,python=PROJECT_ROOT/'.venv/bin/python')
        blocked=[c['label']+': '+c['message'] for c in doctor['checks'] if c['status'] in {'missing','invalid'}]
    elif not (PROJECT_ROOT/'.venv/bin/python').is_file() or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):blocked=['Thiếu Python CLI hoặc FFmpeg/ffprobe.']
    notice='Âm tone kiểm thử; chưa xác minh chất lượng giọng, không gọi giọng thật.' if verification else 'Piper chạy local với model server.' if body.provider=='piper' else 'Nạp model local/có thể tải model, dùng CPU/GPU.' if body.provider=='vieneu' and (read_config().get('VIENEU_MODE') or 'v3turbo')!='remote' else 'Gọi dịch vụ qua mạng; có thể phát sinh chi phí theo provider. Chỉ chạy sau khi xác nhận.'
    reuse=None
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));existing=db.get(Job,identifier)
        if existing:
            if json.loads(existing.config_json).get('request_fingerprint')!=request_hash:raise BookError('Request ID đã dùng cho mẫu khác.')
            return result(existing)
        if not body.force:
            for artifact in db.exec(select(BookArtifact).where(BookArtifact.book_id==str(book_id),BookArtifact.kind=='voice_sample',BookArtifact.source_signature==signature)).all():
                try:book_media(repo,db,book_id,artifact.id,'voice_sample')
                except BookError:continue
                reuse=artifact.id;break
        plan={'action':'voice_sample','configuration':values,'chapters':[],'text':body.text,'source_signature':signature,'tts_fingerprint':fingerprint,
              'voice_catalog_source':metadata['source'],'execution_provider':'fake-tts' if verification else body.provider,'blocked':bool(blocked),'blocked_reasons':blocked,
              'reuse_artifact_id':reuse,'notice':notice,'policies':{'force':body.force,'resume':True}}
        config={'plan':plan,'request_fingerprint':request_hash,'steps':len(TextChunker(max_chars=values['chunk_chars']).chunk_text(body.text))}
        job=Job(id=identifier,book_id=str(book_id),kind='voice_sample',status='preview',config_json=json.dumps(config,sort_keys=True));db.add(job);db.flush();return result(job)


def attach_routes(router,call,verification):
    @router.get('/{book_id}/voices')
    def voices(book_id:UUID,request:Request,provider:Provider=Query(default='vieneu')):
        def action(repo):
            repo.get(book_id);metadata=catalog(provider)
            with session_scope(repo.engine) as db:
                samples=db.exec(select(BookArtifact).where(BookArtifact.book_id==str(book_id),BookArtifact.kind=='voice_sample')).all()
                for voice in metadata['voices']:
                    voice['has_successful_real_sample']=False
                    for sample in samples:
                        info=json.loads(sample.source_manifest)
                        if info.get('provider')==provider and info.get('voice')==voice['id'] and info.get('verification') is False:
                            try:book_media(repo,db,book_id,sample.id,'voice_sample')
                            except BookError:continue
                            voice['has_successful_real_sample']=True;break
            return metadata
        return call(request,action)
    @router.post('/{book_id}/voice-plans',status_code=201)
    def voice_plan(book_id:UUID,body:VoiceRequest,request:Request):return call(request,lambda r:preview(r,book_id,body,verification))
    @router.get('/{book_id}/voice-samples/{artifact_id}')
    def stream(book_id:UUID,artifact_id:UUID,request:Request,download:bool=False):
        def action(repo):
            with session_scope(repo.engine) as db:
                _,path=book_media(repo,db,book_id,artifact_id,'voice_sample')
                return FileResponse(path,media_type='audio/mpeg',filename='voice-sample.mp3' if download else None)
        return call(request,action)
