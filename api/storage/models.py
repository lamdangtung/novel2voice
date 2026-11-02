"""Versioned web data. Legacy CLI tables remain separate and unchanged."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint, CheckConstraint
from src.languages import LANGUAGES


def new_id():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class SchemaVersion(SQLModel, table=True):
    __tablename__ = 'n2v_schema'
    id: int = Field(default=1, primary_key=True)
    version: int


class Book(SQLModel, table=True):
    __tablename__ = 'n2v_books'
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(max_length=200)
    language: str = Field(default='vi', max_length=2)
    create_token: str = Field(unique=True, index=True)
    create_fingerprint: str = ""
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    revision: int = 1
    __table_args__ = (CheckConstraint("language IN (" + ','.join("'"+code+"'" for code in LANGUAGES) + ")"), CheckConstraint('length(trim(name)) > 0'))


class Chapter(SQLModel, table=True):
    __tablename__ = 'n2v_chapters'
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key='n2v_books.id', index=True)
    number: int
    title: str
    source_hash: str
    revision: int = 1
    created_at: str = Field(default_factory=now)
    __table_args__ = (UniqueConstraint('book_id', 'number'), CheckConstraint('number >= 0'))


class Artifact(SQLModel, table=True):
    __tablename__ = 'n2v_artifacts'
    id: str = Field(default_factory=new_id, primary_key=True)
    chapter_id: str = Field(foreign_key='n2v_chapters.id', index=True)
    kind: str  # source_txt / translation_txt / audio; path is relative to managed root
    relative_path: str = Field(unique=True)
    sha256: str
    provenance: str
    verified: bool = False
    created_at: str = Field(default_factory=now)


class Job(SQLModel, table=True):
    __tablename__ = 'n2v_jobs'
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key='n2v_books.id', index=True)
    chapter_id: str | None = Field(default=None, foreign_key='n2v_chapters.id')
    kind: str
    status: str = 'pending'
    config_json: str = '{}'
    created_at: str = Field(default_factory=now)


class LegacyCheckpoint(SQLModel, table=True):
    __tablename__ = 'n2v_legacy_checkpoints'
    id: str = Field(default_factory=new_id, primary_key=True)
    source_sha256: str
    logical_sha256: str
    # A reference for review only; deliberately no chapter/artifact foreign keys.
    source_name: str
    imported_at: str = Field(default_factory=now)


class ImportSession(SQLModel, table=True):
    __tablename__ = 'n2v_import_sessions'
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key='n2v_books.id', index=True)
    status: str = 'preview'
    items_json: str
    result_json: str = '[]'
    created_at: str = Field(default_factory=now)


class BookArtifact(SQLModel, table=True):
    __tablename__ = 'n2v_book_artifacts'
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key='n2v_books.id', index=True)
    job_id: str = Field(foreign_key='n2v_jobs.id', index=True)
    kind: str = 'merged_audio'
    relative_path: str = Field(unique=True)
    sha256: str
    duration: float
    source_signature: str = Field(index=True)
    source_manifest: str
    created_at: str = Field(default_factory=now)
