"""Offline full-library backup/restore into a new destination; no environment keys."""
import argparse,hashlib,json,os,shutil,sqlite3
from pathlib import Path
from uuid import uuid4
from api.maintenance import gate

ALLOWED={'books','job-results','staging','settings.json','deleted-chapters'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def checked_tree(root):
    for path in root.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.stat().st_nlink>1):raise ValueError('Không chấp nhận symlink/hardlink trong backup.')
        yield path

def copy_library(source,target):
    for path in checked_tree(source):
        rel=path.relative_to(source)
        if rel.parts[0] not in ALLOWED:continue
        if path.is_file() and path.suffix!='.lock':
            dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)

def database_check(path,root):
    with sqlite3.connect(path) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Database backup không hợp lệ.')
        for table in ['n2v_artifacts','n2v_book_artifacts']:
            for relative,sha in db.execute(f'SELECT relative_path,sha256 FROM {table}'):
                p=Path(relative)
                if p.is_absolute() or '..' in p.parts or not (root/p).is_file() or digest(root/p)!=sha:raise ValueError('Artifact thiếu hoặc checksum không khớp; sửa trước khi backup/restore.')

def backup(source,destination):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if destination.exists() or destination.is_relative_to(source):raise ValueError('Backup phải ở thư mục mới bên ngoài thư viện.')
    if not (source/'library.sqlite3').is_file():raise ValueError('Không tìm thấy database thư viện.')
    destination.parent.mkdir(parents=True,exist_ok=True);stage=destination.with_name('.'+destination.name+'-'+uuid4().hex)
    with gate(source,exclusive=True):
        stage.mkdir()
        try:
            copy_library(source,stage)
            with sqlite3.connect(source/'library.sqlite3') as src,sqlite3.connect(stage/'library.sqlite3') as dst:src.backup(dst)
            database_check(stage/'library.sqlite3',stage)
            files={str(p.relative_to(stage)):digest(p) for p in checked_tree(stage) if p.is_file()}
            (stage/'backup-manifest.json').write_text(json.dumps({'format':'novel2voice-library-v1','files':files},sort_keys=True,indent=2))
            stage.rename(destination)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return {'destination':str(destination),'files':len(files),'status':'verified'}

def restore(source,destination):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if destination.exists():raise ValueError('Restore chỉ tạo thư mục mới; không ghi đè thư viện.')
    list(checked_tree(source));manifest=json.loads((source/'backup-manifest.json').read_text())
    if manifest.get('format')!='novel2voice-library-v1':raise ValueError('Định dạng backup không được hỗ trợ.')
    for name,sha in manifest['files'].items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or not (source/rel).is_file() or digest(source/rel)!=sha:raise ValueError('Backup thiếu file hoặc checksum sai.')
    database_check(source/'library.sqlite3',source)
    destination.parent.mkdir(parents=True,exist_ok=True);stage=destination.with_name('.'+destination.name+'-'+uuid4().hex);stage.mkdir()
    try:
        for name in manifest['files']:
            dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
        # A restored process must never masquerade as an already running worker.
        with sqlite3.connect(stage/'library.sqlite3') as db:db.execute("UPDATE n2v_jobs SET status='interrupted' WHERE status IN ('running','stop_requested')")
        stage.rename(destination)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return {'destination':str(destination),'status':'verified','notice':'Job đang chạy chuyển interrupted; mở app và xác nhận tiếp tục.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore']);p.add_argument('--source',required=True);p.add_argument('--destination',required=True);args=p.parse_args()
    try:print(json.dumps(globals()[args.action](args.source,args.destination),ensure_ascii=False));return 0
    except Exception as exc:print(str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
