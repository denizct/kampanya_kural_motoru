"""
schemas.py – Pydantic v2 request/response models.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import AksiyonTipi, KuralDurumu, Operator, Parametre


# ── Shared helpers ────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = {"from_attributes": True}


# ── Referans modelleri ────────────────────────────────────────────────────────

class HediyeUrunRead(OrmBase):
    id: int
    stok_kodu: str
    urun_adi: str
    stok_adedi: int
    durum: str


class KuponSablonuRead(OrmBase):
    id: int
    kupon_kodu: str
    indirim_tutari: Decimal
    kullanim_limiti: int
    durum: str


# ── Koşul şemaları ────────────────────────────────────────────────────────────

class KosulCreate(BaseModel):
    parametre: Parametre
    operator: Operator
    deger: str = Field(..., min_length=1, max_length=255)


class KosulRead(OrmBase):
    id: int
    parametre: Parametre
    operator: Operator
    deger: str


# ── Aksiyon şemaları ──────────────────────────────────────────────────────────

class AksiyonCreate(BaseModel):
    aksiyon_tipi: AksiyonTipi
    aksiyon_degeri: Decimal = Field(default=Decimal("0"), ge=0)
    hediye_urun_id: int | None = None
    kupon_sablon_id: int | None = None

    @model_validator(mode="after")
    def validate_aksiyon(self) -> "AksiyonCreate":
        if self.aksiyon_tipi == AksiyonTipi.HEDIYE_URUN_EKLE and not self.hediye_urun_id:
            raise ValueError("HEDIYE_URUN_EKLE aksiyonu için hediye_urun_id zorunludur.")
        if self.aksiyon_tipi == AksiyonTipi.KUPON_TANIMLA and not self.kupon_sablon_id:
            raise ValueError("KUPON_TANIMLA aksiyonu için kupon_sablon_id zorunludur.")
        return self


class AksiyonRead(OrmBase):
    id: int
    aksiyon_tipi: AksiyonTipi
    aksiyon_degeri: Decimal
    hediye_urun_id: int | None
    kupon_sablon_id: int | None
    hediye_urun: HediyeUrunRead | None = None
    kupon_sablonu: KuponSablonuRead | None = None


# ── Kural şemaları ────────────────────────────────────────────────────────────

class KuralCreate(BaseModel):
    kampanya_id: int | None = None
    ad: str = Field(..., min_length=1, max_length=255)
    oncelik_sirasi: int = Field(..., ge=1)
    durum: KuralDurumu = KuralDurumu.AKTIF
    kosullar: list[KosulCreate] = Field(..., min_length=1)
    aksiyon: AksiyonCreate


class KuralRead(OrmBase):
    id: int
    kampanya_id: int | None
    ad: str
    oncelik_sirasi: int
    durum: KuralDurumu
    olusturulma_tarihi: datetime
    kosullar: list[KosulRead]
    aksiyon: AksiyonRead | None


class DurumGuncelle(BaseModel):
    durum: KuralDurumu


class OncelikSiralaItem(BaseModel):
    id: int
    oncelik_sirasi: int = Field(..., ge=1)


class OncelikSiralaRequest(BaseModel):
    kurallar: list[OncelikSiralaItem] = Field(..., min_length=1)


# ── Değerlendirme şemaları ────────────────────────────────────────────────────

GECERLI_KULLANICI_TIPLERI = {"STANDART", "VIP", "PREMIUM", "YENI"}
GECERLI_ODEME_YONTEMLERI = {"KREDI_KARTI", "NAKIT", "HAVALE", "KRIPTO", "BANKA_KARTI"}
GECERLI_HAFTANIN_GUNLERI = {"PAZARTESI", "SALI", "CARSAMBA", "PERSEMBE", "CUMA", "CUMARTESI", "PAZAR"}


class DegerlendirilecekSepet(BaseModel):
    sepet_tutari: Decimal = Field(..., gt=0, description="Sepet tutarı 0'dan büyük olmalıdır.")
    kullanici_tipi: str | None = None
    islem_saati: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    haftanin_gunu: str | None = None
    odeme_yontemi: str | None = None

    @field_validator("kullanici_tipi")
    @classmethod
    def validate_kullanici(cls, v: str | None) -> str | None:
        if v and v.upper() not in GECERLI_KULLANICI_TIPLERI:
            raise ValueError(f"Geçersiz kullanıcı tipi. Kabul edilenler: {GECERLI_KULLANICI_TIPLERI}")
        return v.upper() if v else v

    @field_validator("haftanin_gunu")
    @classmethod
    def validate_gun(cls, v: str | None) -> str | None:
        if v and v.upper() not in GECERLI_HAFTANIN_GUNLERI:
            raise ValueError(f"Geçersiz haftanin_gunu. Kabul edilenler: {GECERLI_HAFTANIN_GUNLERI}")
        return v.upper() if v else v

    @field_validator("odeme_yontemi")
    @classmethod
    def validate_odeme(cls, v: str | None) -> str | None:
        if v and v.upper() not in GECERLI_ODEME_YONTEMLERI:
            raise ValueError(f"Geçersiz ödeme yöntemi. Kabul edilenler: {GECERLI_ODEME_YONTEMLERI}")
        return v.upper() if v else v


class EkFayda(BaseModel):
    tip: str
    detay: str


class DegerlendirmeResponse(BaseModel):
    durum: str  # "ESLESTI" | "ESLESMEDI" | "FALLBACK"
    uygulanan_kural_id: int | None = None
    kampanya_adi: str | None = None
    aksiyon_tipi: str | None = None
    orijinal_tutar: Decimal
    indirim_tutari: Decimal
    odenecek_tutar: Decimal
    ek_fayda: EkFayda | None = None
    fallback_applied: bool = False
    mesaj: str = ""
