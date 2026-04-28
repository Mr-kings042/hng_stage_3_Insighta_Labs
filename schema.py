from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema"""
    username: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    """User response schema"""
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(..., description="UUID v7 identifier")
    github_id: str
    role: str = Field(description="admin or analyst")
    is_active: bool
    last_login_at: Optional[str] = None
    created_at: str


class SessionResponse(BaseModel):
    """Session response schema"""
    id: str
    user_id: str
    issued_at: str
    expires_at: str
    is_revoked: bool
    client_type: str


class TokenResponse(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(BaseModel):
    """Authentication response"""
    status: str = "success"
    user: UserResponse
    tokens: TokenResponse
    is_new_user: bool = False


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """Refresh token response"""
    status: str = "success"
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ProfileBase(BaseModel):
    name: str
    gender: str
    gender_probability: float
    age: int
    age_group: str
    country_id: str
    country_name: str
    country_probability: float

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        if v.lower() not in ["male", "female"]:
            raise ValueError("Gender must be 'male' or 'female'")
        return v.lower()

    @field_validator("age_group")
    @classmethod
    def validate_age_group(cls, v):
        valid_groups = ["child", "teenager", "adult", "senior"]
        if v.lower() not in valid_groups:
            raise ValueError(f"Age group must be one of {valid_groups}")
        return v.lower()


class ProfileCreate(ProfileBase):
    pass


class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(..., description="UUID v7 identifier")
    created_at: str = Field(..., description="ISO 8601 timestamp in UTC")


class ProfileListResponse(BaseModel):
    status: str = "success"
    page: int
    limit: int
    total: int
    total_pages: int
    links: Dict[str, Optional[str]]
    data: List[ProfileResponse]


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str


class SearchQueryResponse(BaseModel):
    status: str = "success"
    page: int
    limit: int
    total: int
    total_pages: int
    links: Dict[str, Optional[str]]
    data: List[ProfileResponse]


class CreateProfileRequest(BaseModel):
    """Request schema for creating a profile"""
    name: str = Field(..., min_length=1, description="Person's name for demographic inference")
    
    @field_validator('name')
    def name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty or whitespace only')
        return v.strip()


class CreateProfileResponse(BaseModel):
    """Response schema for created profile"""
    status: str = "success"
    data: ProfileResponse
