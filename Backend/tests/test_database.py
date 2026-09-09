from datetime import datetime, timezone

from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.core.database import UTCDateTime, _engine_kwargs


class TestEngineKwargs:
    def test_sqlite_gets_check_same_thread(self):
        kwargs = _engine_kwargs("sqlite:///./portal.db")
        assert kwargs == {"connect_args": {"check_same_thread": False}}

    def test_mysql_gets_pool_recycle(self):
        kwargs = _engine_kwargs("mysql+pymysql://u:p@host:3306/db?charset=utf8mb4")
        assert kwargs == {"pool_recycle": 3600}
        assert "connect_args" not in kwargs

    def test_other_dialects_get_nothing(self):
        assert _engine_kwargs("postgresql+psycopg://u:p@host/db") == {}


class TestUTCDateTime:
    def test_roundtrip_normalizes_to_aware_utc(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        metadata = MetaData()
        table = Table(
            "t", metadata,
            Column("id", Integer, primary_key=True),
            Column("d", UTCDateTime),
        )
        metadata.create_all(engine)

        aware = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        naive = datetime(2026, 9, 2, 12, 0)  # mismo wall-clock, sin tz

        with Session(engine) as session:
            session.execute(table.insert(), [{"id": 1, "d": aware}, {"id": 2, "d": naive}])
            session.commit()
            read_aware, read_naive = session.execute(
                table.select().order_by(table.c.id)
            ).scalars().all()

        # Ambos vuelven aware-UTC, sea cual sea el motor.
        assert read_aware.tzinfo is not None and read_aware.utcoffset().total_seconds() == 0
        assert read_naive.tzinfo is not None and read_naive.utcoffset().total_seconds() == 0
        assert read_aware == read_naive

    def test_bind_converts_aware_to_utc_naive(self):
        # Bogotá 07:00 = UTC 12:00: se guarda 12:00 (naive UTC).
        from datetime import timedelta
        bogota = timezone(timedelta(hours=-5))
        value = datetime(2026, 9, 2, 7, 0, tzinfo=bogota)
        bound = UTCDateTime().process_bind_param(value, dialect=None)
        assert bound == datetime(2026, 9, 2, 12, 0)
        assert bound.tzinfo is None

    def test_none_passes_through(self):
        assert UTCDateTime().process_bind_param(None, dialect=None) is None
        assert UTCDateTime().process_result_value(None, dialect=None) is None