from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PortfolioCreate(BaseModel):
    title: str
    url: str
    user_id: int | None = None


class PortfolioUpdate(BaseModel):
    title: str | None = None
    url: str | None = None


class PortfolioFull(PortfolioCreate):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
