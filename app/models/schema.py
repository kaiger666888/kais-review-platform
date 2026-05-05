# Placeholder - will be fully implemented in Task 2
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_tables(conn):
    Base.metadata.create_all(conn)
