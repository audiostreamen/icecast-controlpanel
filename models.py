from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, ForeignKey


class Base(DeclarativeBase):
    pass


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    svc_type: Mapped[str] = mapped_column(String(64), default="Icecast 2 KH")
    owner: Mapped[str] = mapped_column(String(255), default="")
    uid: Mapped[str] = mapped_column(String(64), default="")
    port: Mapped[int] = mapped_column(Integer, default=8000)
    admin_pass: Mapped[str] = mapped_column(String(255), default="")
    source_pass: Mapped[str] = mapped_column(String(255), default="")
    relay_pass: Mapped[str] = mapped_column(String(255), default="")

    limits: Mapped["ServiceLimits"] = relationship(back_populates="service", uselist=False, cascade="all,delete-orphan")
    features: Mapped["ServiceFeatures"] = relationship(back_populates="service", uselist=False, cascade="all,delete-orphan")
    icecast: Mapped["ServiceIcecast"] = relationship(back_populates="service", uselist=False, cascade="all,delete-orphan")
    autodj: Mapped["ServiceAutoDJ"] = relationship(back_populates="service", uselist=False, cascade="all,delete-orphan")
    relay: Mapped["ServiceRelay"] = relationship(back_populates="service", uselist=False, cascade="all,delete-orphan")


class ServiceLimits(Base):
    __tablename__ = "service_limits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    mounts: Mapped[int] = mapped_column(Integer, default=1)
    autodj: Mapped[int] = mapped_column(Integer, default=1)
    bitrate: Mapped[int] = mapped_column(Integer, default=320)
    listeners: Mapped[int] = mapped_column(Integer, default=100)
    bandwidth: Mapped[int] = mapped_column(Integer, default=0)
    storage: Mapped[int] = mapped_column(Integer, default=11000)

    service: Mapped[Service] = relationship(back_populates="limits")


class ServiceFeatures(Base):
    __tablename__ = "service_features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    hist: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    geoip: Mapped[bool] = mapped_column(Boolean, default=False)
    auth: Mapped[bool] = mapped_column(Boolean, default=False)
    multi: Mapped[bool] = mapped_column(Boolean, default=False)
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    social: Mapped[bool] = mapped_column(Boolean, default=False)
    record: Mapped[bool] = mapped_column(Boolean, default=False)

    service: Mapped[Service] = relationship(back_populates="features")


class ServiceIcecast(Base):
    __tablename__ = "service_icecast"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    public_server: Mapped[str] = mapped_column(String(64), default="Default (bron bepaalt)")
    intro_path: Mapped[str] = mapped_column(String(512), default="")
    yp_url: Mapped[str] = mapped_column(String(512), default="")
    redirect_path: Mapped[str] = mapped_column(String(256), default="")

    service: Mapped[Service] = relationship(back_populates="icecast")


class ServiceAutoDJ(Base):
    __tablename__ = "service_autodj"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    autodj_type: Mapped[str] = mapped_column(String(32), default="liquidsoap")
    fade_in: Mapped[int] = mapped_column(Integer, default=0)
    fade_out: Mapped[int] = mapped_column(Integer, default=0)
    fade_min: Mapped[int] = mapped_column(Integer, default=0)
    smart_fade: Mapped[bool] = mapped_column(Boolean, default=False)
    replay_gain: Mapped[bool] = mapped_column(Boolean, default=False)

    service: Mapped[Service] = relationship(back_populates="autodj")


class ServiceRelay(Base):
    __tablename__ = "service_relay"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    relay_type: Mapped[str] = mapped_column(String(64), default="Uitgeschakeld")

    service: Mapped[Service] = relationship(back_populates="relay")
