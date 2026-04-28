from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR
from uuid import UUID as PyUUID
import uuid
from database import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type that uses CHAR(32) for storage."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, PyUUID):
            return value.hex
        if isinstance(value, str):
            return PyUUID(value).hex
        raise TypeError(f"Cannot convert {type(value)} to UUID")

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, PyUUID):
            return value
        return PyUUID(value)


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, unique=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    gender = Column(String(50), nullable=False, index=True)
    gender_probability = Column(Float, nullable=False)
    age = Column(Integer, nullable=False, index=True)
    age_group = Column(String(50), nullable=False, index=True)
    country_id = Column(String(2), nullable=False, index=True)
    country_name = Column(String(255), nullable=False)
    country_probability = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("name", name="uq_profile_name"),
    )

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": str(self.id) if self.id else None,
            "name": self.name,
            "gender": self.gender,
            "gender_probability": self.gender_probability,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "country_name": self.country_name,
            "country_probability": self.country_probability,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(Base):
    """User model for authentication"""
    __tablename__ = "users"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, unique=True)
    github_id = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="analyst", index=True)  # admin or analyst
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": str(self.id) if self.id else None,
            "github_id": self.github_id,
            "username": self.username,
            "email": self.email,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "is_active": self.is_active,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Session(Base):
    """Session/Token model for tracking active sessions"""
    __tablename__ = "sessions"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, unique=True)
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(String(255), nullable=False, index=True)
    access_token_jti = Column(String(255), nullable=True, index=True)  # JWT ID for revocation
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_revoked = Column(Boolean, nullable=False, default=False, index=True)
    client_type = Column(String(50), nullable=False)  # web or cli

    # Relationships
    user = relationship("User", back_populates="sessions")

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": str(self.id) if self.id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_revoked": self.is_revoked,
            "client_type": self.client_type,
        }
