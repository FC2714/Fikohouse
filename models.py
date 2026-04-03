from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    # Connection pooling settings
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True  # Verify connections before using them
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class ManagedEmail(Base):
    __tablename__ = "managed_emails"
    id = Column(Integer, primary_key=True)
    email_address = Column(String, unique=True, nullable=False)
    imap_server = Column(String, nullable=False)   # imap.gmail.com or outlook.office365.com
    app_password_encrypted = Column(String, nullable=False)

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    language = Column(String, nullable=False)   # e.g. English, Türkçe, Español
    subject_text = Column(String, nullable=False)
    active = Column(Boolean, default=True)

# Create database tables
Base.metadata.create_all(bind=engine)