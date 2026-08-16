"""
models.py – SQLAlchemy ORM models for all 6 tables.
"""
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class KuralDurumu(str, enum.Enum):
    AKTIF = "AKTIF"
    PASIF = "PASIF"


class Parametre(str, enum.Enum):
    SEPET_TUTARI = "sepet_tutari"
    KULLANICI_TIPI = "kullanici_tipi"
    ISLEM_SAATI = "islem_saati"
    HAFTANIN_GUNU = "haftanin_gunu"
    ODEME_YONTEMI = "odeme_yontemi"


class Operator(str, enum.Enum):
    ESITTIR = "ESITTIR"
    BUYUKTUR = "BUYUKTUR"
    KUCUKTUR = "KUCUKTUR"
    BUYUK_ESIT = "BUYUK_ESIT"
    KUCUK_ESIT = "KUCUK_ESIT"
    ICINDEDIR = "ICINDEDIR"


class AksiyonTipi(str, enum.Enum):
    YUZDE_INDIRIM = "YUZDE_INDIRIM"
    SABIT_INDIRIM = "SABIT_INDIRIM"
    UCRETSIZ_KARGO = "UCRETSIZ_KARGO"
    HEDIYE_URUN_EKLE = "HEDIYE_URUN_EKLE"
    KUPON_TANIMLA = "KUPON_TANIMLA"


# ── Tables ────────────────────────────────────────────────────────────────────

class HediyeUrun(Base):
    __tablename__ = "hediye_urunler"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stok_kodu: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    urun_adi: Mapped[str] = mapped_column(String(255), nullable=False)
    stok_adedi: Mapped[int] = mapped_column(Integer, default=0)
    durum: Mapped[str] = mapped_column(String(32), default="AKTIF")

    aksiyonlar: Mapped[list["Aksiyon"]] = relationship(back_populates="hediye_urun")


class KuponSablonu(Base):
    __tablename__ = "kupon_sablonlari"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kupon_kodu: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    indirim_tutari: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    kullanim_limiti: Mapped[int] = mapped_column(Integer, default=1)
    durum: Mapped[str] = mapped_column(String(32), default="AKTIF")

    aksiyonlar: Mapped[list["Aksiyon"]] = relationship(back_populates="kupon_sablonu")


class Kampanya(Base):
    __tablename__ = "kampanyalar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ad: Mapped[str] = mapped_column(String(255), nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text, nullable=True)
    baslangic_tarihi: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bitis_tarihi: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    olusturulma_tarihi: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    kurallar: Mapped[list["Kural"]] = relationship(back_populates="kampanya", cascade="all, delete-orphan")


class Kural(Base):
    __tablename__ = "kurallar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kampanya_id: Mapped[int | None] = mapped_column(ForeignKey("kampanyalar.id", ondelete="SET NULL"), nullable=True)
    ad: Mapped[str] = mapped_column(String(255), nullable=False)
    oncelik_sirasi: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    durum: Mapped[KuralDurumu] = mapped_column(
        Enum(KuralDurumu, name="kural_durumu_enum"), default=KuralDurumu.AKTIF, nullable=False
    )
    olusturulma_tarihi: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    kampanya: Mapped["Kampanya | None"] = relationship(back_populates="kurallar")
    kosullar: Mapped[list["Kosul"]] = relationship(back_populates="kural", cascade="all, delete-orphan")
    aksiyon: Mapped["Aksiyon | None"] = relationship(back_populates="kural", cascade="all, delete-orphan", uselist=False)


class Kosul(Base):
    __tablename__ = "kosullar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kural_id: Mapped[int] = mapped_column(ForeignKey("kurallar.id", ondelete="CASCADE"), nullable=False)
    parametre: Mapped[Parametre] = mapped_column(
        Enum(Parametre, name="parametre_enum"), nullable=False
    )
    operator: Mapped[Operator] = mapped_column(
        Enum(Operator, name="operator_enum"), nullable=False
    )
    deger: Mapped[str] = mapped_column(String(255), nullable=False)

    kural: Mapped["Kural"] = relationship(back_populates="kosullar")


class Aksiyon(Base):
    __tablename__ = "aksiyonlar"
    __table_args__ = (UniqueConstraint("kural_id", name="uq_aksiyon_kural"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kural_id: Mapped[int] = mapped_column(ForeignKey("kurallar.id", ondelete="CASCADE"), nullable=False, unique=True)
    aksiyon_tipi: Mapped[AksiyonTipi] = mapped_column(
        Enum(AksiyonTipi, name="aksiyon_tipi_enum"), nullable=False
    )
    aksiyon_degeri: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    hediye_urun_id: Mapped[int | None] = mapped_column(ForeignKey("hediye_urunler.id"), nullable=True)
    kupon_sablon_id: Mapped[int | None] = mapped_column(ForeignKey("kupon_sablonlari.id"), nullable=True)

    kural: Mapped["Kural"] = relationship(back_populates="aksiyon")
    hediye_urun: Mapped["HediyeUrun | None"] = relationship(back_populates="aksiyonlar")
    kupon_sablonu: Mapped["KuponSablonu | None"] = relationship(back_populates="aksiyonlar")
