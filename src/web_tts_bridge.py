"""Private subprocess adapter: API keeps SDK/model dependencies in CLI .venv."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import signal
import threading
import os
import time
from src.web_contract import tts_fingerprint

ROOT=Path(__file__).resolve().parent.parent


def checked(path,root):
    path=Path(path).absolute();root=Path(root).absolute()
    if not path.is_relative_to(root) or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Unsafe bridge path')
    if path.is_file() and path.stat().st_nlink>1:raise ValueError('Unsafe bridge link')
    return path


def run(request,root):
    source=checked(request['source'],root);output=checked(request['output'],root)
    state=checked(request['state_dir'],root);log=checked(request['log'],root)
    values=request['configuration'];verification=request['verification']
    if tts_fingerprint(values,verification)!=request['fingerprint']:raise ValueError('Runtime changed')
    if source.stat().st_size>(2*1024*1024 if request.get('input_kind')=='translation_txt' else 256*1024) or hashlib.sha256(source.read_bytes()).hexdigest()!=request['source_hash']:
        raise ValueError('Source changed')
    if verification:
        from api.verification.providers import FakeTTSProvider, FaultPlan
        fixture=checked(request['fixture'],ROOT/'.verification')
        provider=FakeTTSProvider(fixture,checked(request.get('book_root',str(source.parents[2])),root),log,FaultPlan(delay_ms=request.get('verification_delay_ms',0),fail_on_calls=(request['verification_fail_on_call'],) if request.get('verification_failure') and request.get('verification_fail_on_call') else (),fail_on_chapters=(request['chapter_id'],) if request.get('verification_failure') and not request.get('verification_fail_on_call') else ()),chapter_id=request['chapter_id'])
        provider.voice='verification:'+request['fingerprint']
    else:
        from src.tts import get_tts_provider
        provider=get_tts_provider(provider_name=values['provider'],voice=values['voice'] or None)
        if values['provider']=='openai':provider.client.max_retries=0
    from src.tts_jobs import TTSJobRunner, file_digest
    from src.text_chunker import TextChunker
    from src.audio_merger import AudioMerger
    calls=0
    original=provider.generate_batch
    def counted(tasks,max_concurrency=3,show_progress=True):
        nonlocal calls
        calls+=len(tasks)
        return original(tasks,max_concurrency=max_concurrency,show_progress=show_progress)
    provider.generate_batch=counted
    try:
        runner=TTSJobRunner(provider,AudioMerger(),TextChunker(max_chars=values['chunk_chars']),state,
                            concurrency=values['concurrency'],retries=values['retries'])
        runner.run(source,output,resume=request.get('resume',True) and not request.get('force',False) and not request.get('verification_failure'),cleanup=values['cleanup'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=request['source_hash']:raise ValueError('Source changed')
        return {'status':'completed','provider_calls':getattr(provider,'calls',calls),'provider_signature':runner.signature,'output_sha256':file_digest(output),
                'duration':AudioMerger().get_duration(output),'notice':'Audio kiểm thử (âm tone).' if verification else 'Đã tạo audio bằng provider được chọn.'}
    except KeyboardInterrupt:
        return {'status':'stopped','provider_calls':getattr(provider,'calls',calls),'notice':'Đã dừng ở điểm an toàn, giữ checkpoint và các đoạn hợp lệ.'}
    except Exception:
        return {'status':'failed','provider_calls':getattr(provider,'calls',calls),'error':'TTS_EXECUTION_FAILED','notice':'TTS thất bại; checkpoint được giữ để kiểm tra/chạy lại.'}
    finally:
        if hasattr(provider,'close'):provider.close()


def manifest_root(path):
    roots=[ROOT/'.verification/web',ROOT/'.novel2voice']
    if os.environ.get('NOVEL2VOICE_BRIDGE_ROOT'):
        configured=Path(os.environ['NOVEL2VOICE_BRIDGE_ROOT']).absolute()
        if not (configured/'library.sqlite3').is_file():raise ValueError('Missing configured library')
        roots.append(configured)
    root=next((r for r in roots if path.is_relative_to(r/'job-results')),None)
    if root is None and path.is_relative_to(ROOT/'.verification/workspaces'):
        from api.verification.workspace import WorkspaceManager
        relative=path.relative_to(ROOT/'.verification/workspaces')
        if len(relative.parts)>=5 and relative.parts[1:3]==('web','job-results'):
            manager=WorkspaceManager();manager.describe(relative.parts[0]);root=manager.target(relative.parts[0])/'web'
    if root is None:raise ValueError('Unsafe manifest root')
    checked(path,root)
    return root


def watch_parent(expected_parent):
    signal.signal(signal.SIGUSR1,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    def parent_watch():
        while True:
            if os.getppid()!=expected_parent:
                os.kill(os.getpid(),signal.SIGUSR1);return
            time.sleep(.2)
    threading.Thread(target=parent_watch,daemon=True).start()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);args=parser.parse_args()
    path=Path(args.manifest).absolute()
    root=manifest_root(path)
    request=json.loads(path.read_text())
    watch_parent(request.get('parent_pid',os.getppid()))
    report=path.with_name('bridge-report.json')
    try:result=run(request,root)
    except BaseException:result={'status':'failed','error':'TTS_EXECUTION_FAILED','notice':'Không tạo được audio; kiểm tra môi trường hoặc nội dung rồi thử lại.'}
    temporary=report.with_suffix('.tmp');temporary.write_text(json.dumps(result));temporary.replace(report)
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
