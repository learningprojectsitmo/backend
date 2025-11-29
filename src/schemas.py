from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr | None = None
    first_name: str
    middle_name: str
    last_name: str | None = None

class UserCreate(UserBase):
    password_string: str

class Token(BaseModel):
    access_token: str
    token_type: str

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

class DeleteResponse(BaseModel):
    message: str

