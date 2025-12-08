from pydantic import BaseModel, EmailStr
from typing import Generic, TypeVar, List

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int
    total_pages: int

class Token(BaseModel):
    access_token: str
    token_type: str

class UserBase(BaseModel):
    email: EmailStr | None = None
    first_name: str
    middle_name: str
    last_name: str | None = None

class UserCreate(UserBase):
    password_string: str
    isu_number: int | None = None

class UserFull(UserBase):
    id: int
    isu_number: int | None = None
    tg_nickname: str | None = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True

class UserListItem(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    middle_name: str
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None

    class Config:
        from_attributes = True

class UserListResponse(PaginatedResponse[UserListItem]):
    pass

# Project schemes, TODO move to a separate file in the future

class ProjectCreate(BaseModel):
    name: str
    author_id: int | None = None

class ProjectUpdate(BaseModel):
    name: str | None = None
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None

class ProjectFull(ProjectCreate):
    id: int
    description: str | None = None
    max_participants: int | None = None

    class Config:
        from_attributes = True

class ProjectResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class ProjectListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    max_participants: str | None = None
    author_id: int

    class Config:
        from_attributes = True

class ProjectListResponse(PaginatedResponse[ProjectListItem]):
    pass

#
# Resumes schemas TODO move to a separate file in the future
#

class ResumeCreate(BaseModel):
    header: str
    author_id: int | None = None

class ResumeUpdate(BaseModel):
    header: str | None = None
    resume_text: str | None = None

class ResumeFull(ResumeCreate):
    id: int
    resume_text: str | None = None

    class Config:
        from_attributes = True

class ResumeResponse(BaseModel):
    id: int
    header: str
    author_id: int

    class Config:
        from_attributes = True

class DeleteResponse(BaseModel):
    message: str

class ResumeListResponse(PaginatedResponse[ResumeFull]):
    pass
