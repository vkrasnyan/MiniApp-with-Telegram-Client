from sqlalchemy import Column, String
from .database import Base

class UserSession(Base):
    __tablename__ = "user_sessions"
    session_id = Column(String, primary_key=True, index=True)
    session_data = Column(String)
