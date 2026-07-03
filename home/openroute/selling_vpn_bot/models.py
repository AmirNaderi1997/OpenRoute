from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Numeric, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.services.account_types import ACCOUNT_TYPE_SSH

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # Telegram ID
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str] = mapped_column(String, default="en")
    balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list["SshAccount"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")

class SshServer(Base):
    __tablename__ = "ssh_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    ip_address: Mapped[str] = mapped_column(String)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    dropbear_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    root_password: Mapped[str] = mapped_column(String) # Encrypted
    status: Mapped[str] = mapped_column(String, default="active") # active, offline, maintenance
    service_type: Mapped[str] = mapped_column(String, default=ACCOUNT_TYPE_SSH)

    accounts: Mapped[list["SshAccount"]] = relationship(back_populates="server")

class SshAccount(Base):
    __tablename__ = "ssh_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    server_id: Mapped[int] = mapped_column(ForeignKey("ssh_servers.id"))
    payment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    ssh_username: Mapped[str] = mapped_column(String, unique=True)
    ssh_password: Mapped[str] = mapped_column(String)
    import_link: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    traffic_limit_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traffic_used_gb: Mapped[float] = mapped_column(Numeric(12, 6), default=0.0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="active") # active, expired, disabled
    max_connections: Mapped[int] = mapped_column(Integer, default=1)
    service_type: Mapped[str] = mapped_column(String, default=ACCOUNT_TYPE_SSH)

    user: Mapped["User"] = relationship(back_populates="accounts")
    server: Mapped["SshServer"] = relationship(back_populates="accounts")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    server_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ssh_servers.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String, default="USD")
    payment_method: Mapped[str] = mapped_column(String, default="crypto") # 'crypto', 'card_to_card'
    card_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    gateway_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending") # 'pending', 'completed', 'failed'
    service_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="payments")


class DiscountCode(Base):
    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    percent_off: Mapped[int] = mapped_column(Integer)
    payment_method_scope: Mapped[str] = mapped_column(String, default="all")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="open") # open, in_progress, resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")

class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id"))
    sender: Mapped[str] = mapped_column(String) # 'user', 'admin'
    text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")
