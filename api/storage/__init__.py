"""SQLite sessions with foreign keys and explicit schema version checks."""
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine
from api.storage.models import SchemaVersion

SCHEMA_VERSION = 3


def engine_for(path):
    path = Path(path)
    engine = create_engine('sqlite:///' + str(path), connect_args={'check_same_thread': False, 'timeout': 5})
    @event.listens_for(engine, 'connect')
    def sqlite_setup(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=5000')
    return engine


def initialize(engine):
    # Only new databases are initialised here. Legacy upgrades use migration.py.
    from sqlalchemy import inspect
    tables = inspect(engine).get_table_names()
    if tables and 'n2v_schema' not in tables:
        raise ValueError('Database cũ cần nâng cấp trên bản sao; không tự nâng cấp tại chỗ.')
    if 'n2v_schema' in tables:
        with Session(engine) as session:
            version = session.get(SchemaVersion, 1)
            current=version.version if version is not None else None
        if current in {1,2}:
            upgrade_from_one(engine)
        elif current!=SCHEMA_VERSION:
            raise ValueError('Schema version không được hỗ trợ.')
        return
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SchemaVersion(version=SCHEMA_VERSION)); session.commit()


@contextmanager
def session_scope(engine):
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


def upgrade_from_one(engine):
    """Upgrade schema1/2 to multilingual schema3 with a consistent backup and rollback."""
    import sqlite3
    from uuid import uuid4
    from api.storage.models import BookArtifact,Book
    from sqlalchemy.schema import CreateTable
    path=Path(engine.url.database)
    backup=path.with_name(path.name+'.schema-'+uuid4().hex[:8]+'.backup')
    # Caller owns schema.lock. SQLite backup includes committed WAL changes.
    backup.touch(exist_ok=False)
    raw=engine.raw_connection()
    try:
        destination=sqlite3.connect(backup)
        try:raw.driver_connection.backup(destination)
        finally:destination.close()
    finally:raw.close()
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        connection.commit()
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            # SQLite CHECK constraints require rebuilding the parent table. Keep all
            # IDs/columns and recreate its unique index before checking every FK.
            ddl=str(CreateTable(Book.__table__).compile(engine)).replace('CREATE TABLE n2v_books', 'CREATE TABLE n2v_books_v3',1)
            connection.exec_driver_sql(ddl)
            columns=','.join('"'+column.name+'"' for column in Book.__table__.columns)
            connection.exec_driver_sql(f'INSERT INTO n2v_books_v3 ({columns}) SELECT {columns} FROM n2v_books')
            connection.exec_driver_sql('DROP TABLE n2v_books')
            connection.exec_driver_sql('ALTER TABLE n2v_books_v3 RENAME TO n2v_books')
            for index in Book.__table__.indexes:index.create(connection)
            BookArtifact.__table__.create(connection,checkfirst=True)
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():raise ValueError('Quan hệ dữ liệu không hợp lệ sau nâng cấp.')
            connection.exec_driver_sql('UPDATE n2v_schema SET version=? WHERE id=1 AND version IN (1,2)',(SCHEMA_VERSION,))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()
