"""
models.py – SQLAlchemy ORM models and Enums for the Campaign Rule Engine.
"""
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Numeric, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)



class KuralDurumu(str, Enum):
    AKTIF = "AKTIF"
    PASIF = "PASIF"


class ParametreAdi(str, Enum):
    SEPET_TUTARI = "sepet_tutari"
    KULLANICI_TIPI = "kullanici_tipi"
    ISLEM_SAATI = "islem_saati"
    HAFTANIN_GUNU = "haftanin_gunu"
    ODEME_YONTEMI = "odeme_yontemi"


class OperatorTipi(str, Enum):
    ESITTIR = "=="
    BUYUK_ESIT = ">="
    KUCUK_ESIT = "<="
    BUYUKTUR = ">"
    KUCUKTUR = "<"
    ICINDEDIR = "ICINDEDIR"


class AksiyonTipi(str, Enum):
    YUZDE_INDIRIM = "YUZDE_INDIRIM"
    SABIT_INDIRIM = "SABIT_INDIRIM"
    UCRETSIZ_KARGO = "UCRETSIZ_KARGO"
    HEDIYE_URUN_EKLE = "HEDIYE_URUN_EKLE"
    KUPON_TANIMLA = "KUPON_TANIMLA"


class KullaniciTipi(str, Enum):
    VIP = "VIP"
    STANDART = "STANDART"
    YENI = "YENI"


class OdemeYontemi(str, Enum):
    KREDI_KARTI = "KREDI_KARTI"
    HAVALE = "HAVALE"
    KAPIDA_ODEME = "KAPIDA_ODEME"


class HaftaninGunu(str, Enum):
    PAZARTESI = "PAZARTESI"
    SALI = "SALI"
    CARSAMBA = "CARSAMBA"
    PERSEMBE = "PERSEMBE"
    CUMA = "CUMA"
    CUMARTESI = "CUMARTESI"
    PAZAR = "PAZAR"


class Kampanya(Base):
    __tablename__ = "kampanyalar"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ad = Column(String(255), nullable=False)
    aciklama = Column(Text, nullable=True)
    baslangic_tarihi = Column(DateTime, nullable=False, default=utc_now)
    bitis_tarihi = Column(DateTime, nullable=False)
    olusturulma_tarihi = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    kurallar = relationship("Kural", back_populates="kampanya", cascade="all, delete-orphan")


class Kural(Base):
    __tablename__ = "kurallar"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kampanya_id = Column(Integer, ForeignKey("kampanyalar.id", ondelete="SET NULL"), nullable=True)
    ad = Column(String(255), nullable=False)
    oncelik_sirasi = Column(Integer, nullable=False, index=True)
    durum = Column(String(20), nullable=False, default=KuralDurumu.PASIF.value)
    olusturulma_tarihi = Column(DateTime, nullable=False, default=utc_now)

    # Relationships
    kampanya = relationship("Kampanya", back_populates="kurallar")
    kosullar = relationship("Kosul", back_populates="kural", cascade="all, delete-orphan", order_by="Kosul.id")
    aksiyon = relationship("Aksiyon", back_populates="kural", cascade="all, delete-orphan", uselist=False)


class Kosul(Base):
    __tablename__ = "kosullar"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kural_id = Column(Integer, ForeignKey("kurallar.id", ondelete="CASCADE"), nullable=False)
    parametre = Column(String(50), nullable=False)
    operator = Column(String(20), nullable=False)
    deger = Column(String(255), nullable=False)

    # Relationships
    kural = relationship("Kural", back_populates="kosullar")


class Aksiyon(Base):
    __tablename__ = "aksiyonlar"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kural_id = Column(Integer, ForeignKey("kurallar.id", ondelete="CASCADE"), nullable=False, unique=True)
    aksiyon_tipi = Column(String(50), nullable=False)
    aksiyon_degeri = Column(Numeric(10, 2), nullable=True)
    hediye_urun_id = Column(Integer, ForeignKey("hediye_urunler.id", ondelete="SET NULL"), nullable=True)
    kupon_sablon_id = Column(Integer, ForeignKey("kupon_sablonlari.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    kural = relationship("Kural", back_populates="aksiyon")
    hediye_urun = relationship("HediyeUrun", back_populates="aksiyonlar")
    kupon_sablon = relationship("KuponSablon", back_populates="aksiyonlar")


class HediyeUrun(Base):
    __tablename__ = "hediye_urunler"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    stok_kodu = Column(String(100), nullable=False, unique=True)
    urun_adi = Column(String(255), nullable=False)
    stok_adedi = Column(Integer, nullable=False, default=0)
    durum = Column(String(20), nullable=False, default="AKTIF")

    # Relationships
    aksiyonlar = relationship("Aksiyon", back_populates="hediye_urun")


class KuponSablon(Base):
    __tablename__ = "kupon_sablonlari"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kupon_kodu = Column(String(100), nullable=False, unique=True)
    indirim_tutari = Column(Numeric(10, 2), nullable=False)
    kullanim_limiti = Column(Integer, nullable=False, default=0)
    durum = Column(String(20), nullable=False, default="AKTIF")

    # Relationships
    aksiyonlar = relationship("Aksiyon", back_populates="kupon_sablon")
