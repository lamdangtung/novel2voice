"""Private EN→VI adapter. Retry is whole chapter; partial text is never published."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from src.web_tts_bridge import checked,manifest_root,watch_parent
from src.translation_contract import identity,prompt
from src.glossary import Glossary
from src.text_chunker import TextChunker
from src.doctor import read_config


def run(request,root):
    source=checked(request['source'],root);output=checked(request['output'],root);log=checked(request['log'],root)
    if source.stat().st_size>256*1024 or hashlib.sha256(source.read_bytes()).hexdigest()!=request['source_hash']:raise ValueError('Source changed')
    values=request['configuration'];entries=request['glossary_entries'];actual=identity(values,entries,request['verification'],request.get('source_language','en'))
    if actual['translation_fingerprint']!=request['fingerprint']:raise ValueError('Translation runtime changed')
    glossary=Glossary();glossary.entries={e['en']:e['vi'] for e in entries}
    with log.open('a') as stream:stream.write(json.dumps({'status':'attempt','retry_scope':'whole_chapter'})+'\n')
    if request['verification']:
        from api.verification.providers import FakeTranslator,FaultPlan
        failed=request.get('verification_failure',False);call=request.get('verification_fail_on_call')
        translator=FakeTranslator(output.parent,log,FaultPlan(delay_ms=request.get('verification_delay_ms',0),fail_on_calls=(call or 2,) if failed else ()),
                                  chapter_id=request['chapter_id'],glossary=glossary,model=values['translation_model'],prompt_hash=actual['prompt_hash'],glossary_hash=actual['glossary_hash'])
    else:
        env=read_config()
        if not (env.get('OPENAI_API_KEY') or '').strip():raise ValueError('Missing key')
        from src.translator import NovelTranslator
        translator=NovelTranslator(api_key=env['OPENAI_API_KEY'],base_url=env.get('OPENAI_BASE_URL') or None,model=values['translation_model'],glossary=glossary,source_language=request.get('source_language','en'))
        translator.client.max_retries=0
        if hashlib.sha256(translator._build_system_prompt().encode()).hexdigest()!=actual['prompt_hash']:raise ValueError('Prompt contract mismatch')
    chunks=TextChunker(max_chars=values['chunk_chars']).chunk_text(source.read_text(encoding='utf-8-sig'))
    output_parts=[];calls=0;completed=0
    def event(status,index,**extra):
        with log.open('a') as stream:stream.write(json.dumps({'provider':'translator','status':status,'chunk_index':index,'model':values['translation_model'],**actual,**extra})+'\n')
    try:
        for index,chunk in enumerate(chunks,1):
            calls+=1
            if request['verification']:translated=translator.translate_text(chunk,chapter_id=request['chapter_id'],chunk_index=index)
            else:
                event('started',index,input_sha256=hashlib.sha256(chunk.encode()).hexdigest())
                translated=translator.translate_chunk(chunk)
                event('completed',index)
            if not translated.strip():raise ValueError('Empty translation')
            output_parts.append(translated);completed+=1
            if sum(len(p.encode()) for p in output_parts)>2*1024*1024:raise ValueError('Translation too large')
        text='\n\n'.join(output_parts)
        if len(text.encode())>2*1024*1024:raise ValueError('Translation too large')
        if not text.strip() or hashlib.sha256(source.read_bytes()).hexdigest()!=request['source_hash']:raise ValueError('Invalid final translation')
        temporary=checked(output.with_suffix('.partial'),root);temporary.write_text(text,encoding='utf-8');temporary.replace(output)
        return {'status':'completed','provider_calls':calls,'completed_steps':completed,'steps':len(chunks),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),**actual,
                'model':values['translation_model'],'retry_scope':'whole_chapter','notice':'Bản dịch kiểm thử; không phải kết quả AI thật.' if request['verification'] else 'Đã dịch và lưu bản riêng.'}
    except KeyboardInterrupt:
        return {'status':'stopped','provider_calls':calls,'completed_steps':completed,'steps':len(chunks),'retry_scope':'whole_chapter','notice':'Đã dừng dịch. Phần chưa hoàn tất không công bố; tiếp tục sẽ dịch lại toàn chương.'}
    except Exception:
        return {'status':'failed','provider_calls':calls,'completed_steps':completed,'steps':len(chunks),'retry_scope':'whole_chapter','error':'TRANSLATION_FAILED','notice':'Chưa có bản dịch hoàn chỉnh; retry sẽ dịch lại toàn chương, có thể phát sinh lại chi phí.'}
    finally:
        client=getattr(translator,'client',None)
        if client is not None and hasattr(client,'close'):client.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);args=parser.parse_args()
    path=Path(args.manifest).absolute();root=manifest_root(path);request=json.loads(path.read_text());watch_parent(request.get('parent_pid',os.getppid()))
    try:report=run(request,root)
    except BaseException:report={'status':'failed','error':'TRANSLATION_FAILED','notice':'Không dịch được. Kiểm tra key/model/endpoint; chưa gọi lại tự động.','retry_scope':'whole_chapter'}
    output=path.with_name('bridge-report.json');temporary=checked(output.with_suffix('.tmp'),root);temporary.write_text(json.dumps(report));temporary.replace(output)
    return 0 if report['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
