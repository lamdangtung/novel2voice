"""T05 book repository and local API. Content lives under UUIDs, never titles."""
import hashlib
import json
from pathlib import Path
import threading
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, func
from api.storage import engine_for, initialize, session_scope
from api.storage.models import Book, Chapter, Artifact, now
from src.languages import LANGUAGES, validate_language
from api.verification.workspace import PROJECT_ROOT


class BookInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=2,max_length=2)

    @field_validator('language')
    @classmethod
    def clean_language(cls,value):
        return validate_language(value)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Tên truyện không được rỗng hoặc chứa ký tự điều khiển.')
        return value


class CreateBook(BookInput):
    request_id: UUID


class EditBook(BookInput):
    revision: int = Field(ge=1)


class BookView(BaseModel):
    id: str
    name: str
    language: str
    created_at: str
    updated_at: str
    revision: int
    storage: str


class BookList(BaseModel):
    items: list[BookView]
    total: int


class BookError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message); self.status=status


def safe_directory(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BookError('Vùng dữ liệu không được là symlink.', 409)
    path.mkdir(parents=True, exist_ok=True)
    return path


class BookRepository:
    def __init__(self, root):
        self.root=safe_directory(root)
        path=self.root/'library.sqlite3'
        if path.is_symlink() or (path.exists() and path.stat().st_nlink>1):
            raise BookError('Database không được là symlink/hardlink.')
        self.engine=engine_for(path)
        # Serialise first-time initialisation across API processes too.
        import fcntl
        lock=self.root/'schema.lock'
        if lock.is_symlink() or (lock.exists() and lock.stat().st_nlink>1):
            raise BookError('Khóa schema không hợp lệ.')
        with lock.open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:initialize(self.engine)
            except BaseException:
                self.engine.dispose();raise
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

    def view(self, book):
        return BookView(**book.model_dump(),storage='books/'+book.id)

    def list(self, offset=0, limit=100):
        with Session(self.engine) as s:
            rows=s.exec(select(Book).order_by(Book.created_at,Book.id).offset(offset).limit(limit)).all()
            total=s.exec(select(func.count()).select_from(Book)).one()
            return BookList(items=[self.view(x) for x in rows],total=total)

    def get(self, identifier):
        with Session(self.engine) as s:
            book=s.get(Book,str(identifier))
            if not book:raise BookError('Không tìm thấy bộ truyện.',404)
            return self.view(book)

    def create(self, data):
        token=str(data.request_id)
        fingerprint=hashlib.sha256(json.dumps([data.name,data.language],ensure_ascii=False).encode()).hexdigest()
        def existing():
            with Session(self.engine) as s:
                book=s.exec(select(Book).where(Book.create_token==token)).first()
                if book:
                    if book.create_fingerprint!=fingerprint:raise BookError('Mã yêu cầu đã dùng cho nội dung khác. Tải lại form.')
                    safe_directory(self.root/'books'/book.id)
                    return self.view(book)
        previous=existing()
        if previous:return previous
        try:
            with session_scope(self.engine) as s:
                book=Book(name=data.name,language=data.language,create_token=token,create_fingerprint=fingerprint)
                s.add(book);s.flush()
                safe_directory(self.root/'books'/book.id)
                result=self.view(book)
            return result
        except IntegrityError:
            previous=existing()
            if previous:return previous
            raise

    def edit(self, identifier, data):
        with session_scope(self.engine) as s:
            previous=s.get(Book,str(identifier));old_language=previous.language if previous else None
            result=s.exec(update(Book).where(Book.id==str(identifier),Book.revision==data.revision)
                          .values(name=data.name,language=data.language,updated_at=now(),revision=Book.revision+1))
            if result.rowcount!=1:
                if s.get(Book,str(identifier)) is None:raise BookError('Không tìm thấy bộ truyện.',404)
                raise BookError('Thông tin đã thay đổi ở cửa sổ khác. Tải lại trước khi lưu.')
            if old_language!=data.language:
                chapter_ids=select(Chapter.id).where(Chapter.book_id==str(identifier))
                s.exec(update(Artifact).where(Artifact.chapter_id.in_(chapter_ids),Artifact.kind.in_(['translation_txt','audio'])).values(verified=False))
                s.exec(update(Chapter).where(Chapter.book_id==str(identifier)).values(revision=Chapter.revision+1))
        return self.get(identifier)


class RepositoryProvider:
    def __init__(self, settings):
        self.settings=settings;self.lock=threading.Lock();self.repository=None

    def __call__(self, request):
        with self.lock:
            if self.repository is None:
                root=self.settings.data_dir or PROJECT_ROOT/('.verification/web' if self.settings.verification_enabled else '.novel2voice')
                self.repository=BookRepository(root)
                self.repository.verification_enabled=self.settings.verification_enabled
                request.app.state.repository=self.repository
        return self.repository


def create_router(settings, provider=None):
    router=APIRouter(prefix='/api/v1/books',tags=['Books'])
    repo=provider or RepositoryProvider(settings)

    def call(request, action):
        try:return action(repo(request))
        except BookError as exc:raise HTTPException(exc.status, str(exc))

    @router.get('/workspace/languages')
    def languages():
        return {'items':[{'code':code,'label':label} for code,label in LANGUAGES.items()],'translation_target':'vi'}

    @router.get('',response_model=BookList)
    def books(request:Request,offset:int=Query(default=0,ge=0),limit:int=Query(default=100,ge=1,le=100)):
        return call(request,lambda r:r.list(offset,limit))

    @router.post('',response_model=BookView,status_code=201)
    def create(data:CreateBook,request:Request):
        return call(request,lambda r:r.create(data))

    @router.get('/{book_id}',response_model=BookView)
    def get(book_id:UUID,request:Request):
        return call(request,lambda r:r.get(book_id))

    @router.patch('/{book_id}',response_model=BookView)
    def edit(book_id:UUID,data:EditBook,request:Request):
        return call(request,lambda r:r.edit(book_id,data))
    from api.connections import attach_routes as attach_connections
    attach_connections(router,call)
    from api.configuration import attach_routes as attach_configuration
    attach_configuration(router, call)
    from api.glossaries import attach_routes as attach_glossaries
    attach_glossaries(router, call)
    from api.voices import attach_routes as attach_voices
    attach_voices(router,call,settings.verification_enabled)
    from api.merged_audio import attach_routes as attach_merged
    attach_merged(router,call)
    from api.audio_downloads import attach_routes as attach_downloads
    attach_downloads(router,call)
    from api.audio_imports import attach_routes as attach_audio
    attach_audio(router, call)
    from api.imports import attach_routes
    attach_routes(router, call, settings.verification_enabled)
    return router
