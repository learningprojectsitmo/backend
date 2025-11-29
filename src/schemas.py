from pydantic import BaseModel, EmailStr

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


class DeleteResponse(BaseModel):
    message: str

