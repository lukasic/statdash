from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from app.core.database import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    ssh_command_prefix: Mapped[str] = mapped_column(String(64), default="ssh", server_default="ssh", nullable=False)
