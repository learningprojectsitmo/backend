from typing import List, Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship # DeclarativeBase, 
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# class Base(DeclarativeBase):
#    pass

class User(Base):
    __tablename__ = "user"
    # using "id" instead of "user_id" to avoid "user.user_id"
    id: Mapped[int] = mapped_column(primary_key=True)
    # I am splitting fullname into three attributes in order to avoid troubles with incorrect "FIO" input format
    # and to make it easier to address a user by their first (or first+last) name (could be useful in the interface)
    # eg: notification from the user with the role teacher would be displayed as "First Last";
    # notification from the student would be "First Middle[0]."
    first_name: Mapped[str] = mapped_column(String(30), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(40), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    email: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    password_hashed: Mapped[str] = mapped_column(String, nullable=False)

    isu_number: Mapped[int | None] = mapped_column(nullable=True)
    tg_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)

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
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    header: Mapped[str]
    # I think resume should be stored in .md or .html (if we want to allow advanced formatting)
    # In the current system the resume editor is cumbersome, I would like to see it simplified. 
    # .md is perfect (you write plain text with no distractions), but .html can be allowed alongside for creativity..
    # The question is how will images be storred? since they are supported by both markdown and html..
    # And how will the switcher "md | html" in the editor work? the translation is too complex and will enevitably 
    # cause partial data loss. it should be on the user's shoulder to translate from one language to another, so that 
    # we are not responsible the the information loss 
    resume_text: Mapped[str | None] = mapped_column(nullable=True)
    # roles: what student wants to do. it should be here and not in the "Response.note", because we want to be able to filter students by roles and perform automatic distribution

    user: Mapped["User"] = relationship(back_populates="resumes")

    def __repr__(self) -> str:
        return f"Resume(id={self.id!r}, user_id={self.user_id!r}, resume_text={self.resume_text!r})"

# class Role(Base):
# will be used in both Resumes and project descriptions. 
# what students want to do (generally) <-> what projects need. will be convenient for filtering and automatic distribution
# note that is it not the same as skills
# in automatic distribution we will have match priority:
# skills (ideally they should match)
# roles (at least roles should match)
# random

class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    # should description be in markdown too?
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
        return f"Resume(id={self.id!r}, author_id={self.author_id!r}, description={self.description!r})"


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


# class SkillTag(Base):
# the problem with tags in resume now is that there are duplicates. how to avoid them? 
# firstly - store lowecase of everything (GIT = Git = git), trim spaces etc
# secondly - force somehow advanced checking.. or store a range of possible names (eg Linux, GNU/Linux, UNIX, Линукс, линукс idk..)

# class InterestTag(Base):
# same notes as for the SkillTag
