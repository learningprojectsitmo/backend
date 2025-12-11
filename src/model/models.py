from typing import List, Optional
from sqlalchemy import ForeignKey, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship # DeclarativeBase,
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(30), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(40), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    email: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    isu_number: Mapped[int | None] = mapped_column(nullable=True)
    tg_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)

    password_hashed: Mapped[str] = mapped_column(String, nullable=False)

    resumes: Mapped[list["Resume"]] = relationship(
            back_populates="user", cascade="all, delete-orphan" 
    )
    responses: Mapped[list["Response"]] = relationship(
        back_populates="respondent", cascade="all, delete-orphan" 
    )
    projects_led: Mapped[list["Project"]] = relationship(
        # The project will not be deleted when its author gets deleted
        back_populates="author"
    )
    projects_in: Mapped[list['ProjectParticipation']] = relationship(
        back_populates='participant', cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, first_name={self.first_name!r}, isu_number={self.isu_number!r})"


class Resume(Base):
    __tablename__ = "resume"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    header: Mapped[str] = mapped_column(nullable=False)
    resume_text: Mapped[str | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(back_populates="resumes")

    # skills (particular, like docker, git etc.)
    # roles (general, like backend, Project Management etc.)

    def __repr__(self) -> str:
        return (
            f"Resume(id={self.id!r}, "
            f"author_id={self.author_id!r}, "
            f"header={self.header!r})"
        )


class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    max_participants: Mapped[str | None] = mapped_column(nullable=True)

    author: Mapped["User"] = relationship(back_populates="projects_led")
    responses: Mapped[list["Response"]] = relationship(
        # TODO do we want to store responses to a deleted project?
        back_populates="project", cascade="all, delete-orphan"
    )

    # status_id (for later, need to create the Status table first)
    # skills (particular, like docker, git etc.)
    # roles (general, like backend, Project Management etc.)
    participants: Mapped[list['ProjectParticipation']] = relationship(back_populates='project')

    def __repr__(self) -> str:
        return f"Project(id={self.id!r}, author_id={self.author_id!r}, description={self.description!r})"


class ProjectParticipation(Base):
    __tablename__ = 'project_participation'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    project: Mapped['Project'] = relationship(back_populates='participants')
    participant: Mapped['User'] = relationship(back_populates='projects_in')


class Response(Base):
    __tablename__ = "response"
    id: Mapped[int] = mapped_column(primary_key=True)
    respondent_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    note: Mapped[str] = mapped_column(String(200), nullable=True)

    # TODO not all relationships are needed. Remove unneeded
    respondent: Mapped["User"] = relationship(back_populates="responses")
    project: Mapped["Project"] = relationship(back_populates="responses")

    def __repr__(self) -> str:
        return f"Response(id={self.id!r}, respondent_id={self.respondent_id!r}, note={self.note!r})"


