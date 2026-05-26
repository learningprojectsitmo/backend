from __future__ import annotations

from datetime import datetime
from re import sub

from pydantic import BaseModel, ConfigDict


def to_camel(s: str) -> str:
    return sub(r"_([a-z])", lambda m: m.group(1).upper(), s)


class IdeaAuthorResponse(BaseModel):
    id: int
    username: str | None = None

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class IdeaTagResponse(BaseModel):
    id: int
    name: str
    count: int = 0

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class IdeaCommentResponse(BaseModel):
    id: int
    author: IdeaAuthorResponse
    text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class IdeaListItem(BaseModel):
    id: int
    title: str
    description: str
    votes: int
    user_vote: str | None = None
    comments_count: int = 0
    tags: list[str] = []
    status: str
    author: IdeaAuthorResponse
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class IdeaFullResponse(BaseModel):
    id: int
    title: str
    description: str
    votes: int
    user_vote: str | None = None
    comments_count: int = 0
    tags: list[str] = []
    status: str
    author: IdeaAuthorResponse
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class IdeaCreate(BaseModel):
    title: str
    description: str
    tags: list[str] = []


class IdeaVoteRequest(BaseModel):
    direction: str  # "up" or "down"


class IdeaCommentCreate(BaseModel):
    text: str


class IdeaTagCreate(BaseModel):
    name: str


class IdeaListResponse(BaseModel):
    items: list[IdeaListItem]
    total: int
    page: int
    limit: int
    total_pages: int
