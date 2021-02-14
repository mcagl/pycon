from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import select

from users.domain.entities import User
from users.domain.paginable import Paginable


class AbstractTransaction:
    session: Any

    def with_session(self, session):
        self.session = session

    def transaction(self):
        raise NotImplementedError()

    async def commit(self):
        raise NotImplementedError()

    async def rollback(self):
        raise NotImplementedError()


class AbstractUsersRepository(AbstractTransaction):
    async def get_by_email(self, email: str) -> Optional[User]:
        raise NotImplementedError()

    async def get_by_id(self, id: int) -> Optional[User]:
        raise NotImplementedError()

    async def create_user(self, user: User) -> User:
        raise NotImplementedError()


class UsersRepository(AbstractUsersRepository):
    session: Optional[AsyncSession]

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self.session = session

    async def get_users(self) -> Paginable[User]:
        return Paginable(self.session, User)

    async def get_by_email(self, email: str) -> Optional[User]:
        query = select(User).where(User.email == email)
        user = (await self.session.execute(query)).scalar_one_or_none()
        return user

    async def get_by_id(self, id: int) -> Optional[User]:
        query = select(User).where(User.id == id)
        user = (await self.session.execute(query)).scalar_one_or_none()
        return user

    async def create_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def search(self, search: str) -> list[User]:
        if not search:
            return []

        query = select(User).where(
            User.fullname.ilike(f"%{search}%")
            | User.name.ilike(f"%{search}%")
            | User.email.ilike(f"%{search}%")
        )
        users = (await self.session.execute(query)).scalars().all()
        return users

    def transaction(self):
        return self.session.begin()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
