from sqlmodel import Session, SQLModel, create_engine

from server.config import DATA_DIR, get_database_url


def create_db_engine():
    database_url = get_database_url()
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url)


engine = create_db_engine()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
