"""
schemas.py – Pydantic v2 validation models and DTO schemas.
"""
import re
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from app.models import (
    KuralDurumu, ParametreAdi, OperatorTipi, AksiyonTipi,
    KullaniciTipi, OdemeYontemi, HaftaninGunu
)

TIME_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# -------------------------------------------------------------
# Sepet Değerlendirme (Evaluation) Şemaları
# -------------------------------------------------------------
class SepetDegerlendirRequest(BaseModel):
    sepet_tutari: float = Field(..., ge=0, description="Sepet toplam tutarı (>= 0)")
    kullanici_tipi: KullaniciTipi = Field(..., description="Kullanıcı segmenti (VIP, STANDART, YENI)")
    islem_saati: str = Field(..., description="İşlem saati (HH:mm formatında)")
    haftanin_gunu: HaftaninGunu = Field(..., description="Haftanın günü (PAZARTESI...PAZAR)")
    odeme_yontemi: OdemeYontemi = Field(..., description="Ödeme yöntemi")

    @field_validator("islem_saati")
    @classmethod
    def validate_islem_saati(cls, v: str) -> str:
        v = v.strip()
        if not TIME_REGEX.match(v):
            raise ValueError("islem_saati 'HH:mm' formatında olmalıdır (örn: 14:30)")
        return v


class EkFayda(BaseModel):
    tip: str
    detay: Optional[Dict[str, Any]] = None
    aciklama: Optional[str] = None


class SepetDegerlendirResponse(BaseModel):
    uygulanan_kural_id: Optional[int] = None
    kampanya_adi: Optional[str] = None
    aksiyon_tipi: Optional[str] = None
    orijinal_tutar: float
    indirim_tutari: float = 0.0
    odenecek_tutar: float
    ek_fayda: Optional[Dict[str, Any]] = None
    fallback_applied: bool = False
    mesaj: Optional[str] = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[Any] = None


# -------------------------------------------------------------
# Koşul Şemaları
# -------------------------------------------------------------
class KosulBase(BaseModel):
    parametre: ParametreAdi
    operator: OperatorTipi
    deger: str

    @model_validator(mode="after")
    def validate_parametre_operator_compatibility(self):
        param = self.parametre
        op = self.operator
        val = self.deger.strip()

        if param == ParametreAdi.SEPET_TUTARI:
            if op not in [OperatorTipi.BUYUK_ESIT, OperatorTipi.KUCUK_ESIT,
                          OperatorTipi.BUYUKTUR, OperatorTipi.KUCUKTUR, OperatorTipi.ESITTIR]:
                raise ValueError(f"sepet_tutari parametresi için '{op.value}' operatörü geçersizdir.")
            try:
                num = float(val)
                if num < 0:
                    raise ValueError("sepet_tutari koşul değeri negatif olamaz.")
            except ValueError:
                raise ValueError("sepet_tutari için geçerli bir sayısal değer girilmelidir.")

        elif param == ParametreAdi.KULLANICI_TIPI:
            if op != OperatorTipi.ESITTIR:
                raise ValueError("kullanici_tipi için yalnızca '==' operatörü desteklenir.")
            valid_vals = [e.value for e in KullaniciTipi]
            if val not in valid_vals:
                raise ValueError(f"kullanici_tipi değeri {valid_vals} listesinden seçilmelidir.")

        elif param == ParametreAdi.ODEME_YONTEMI:
            if op != OperatorTipi.ESITTIR:
                raise ValueError("odeme_yontemi için yalnızca '==' operatörü desteklenir.")
            valid_vals = [e.value for e in OdemeYontemi]
            if val not in valid_vals:
                raise ValueError(f"odeme_yontemi değeri {valid_vals} listesinden seçilmelidir.")

        elif param == ParametreAdi.HAFTANIN_GUNU:
            if op not in [OperatorTipi.ESITTIR, OperatorTipi.ICINDEDIR]:
                raise ValueError("haftanin_gunu için yalnızca '==' veya 'ICINDEDIR' operatörü desteklenir.")
            valid_days = [e.value for e in HaftaninGunu]
            if op == OperatorTipi.ESITTIR:
                if val not in valid_days:
                    raise ValueError(f"haftanin_gunu değeri geçerli bir gün olmalıdır ({valid_days}).")
            elif op == OperatorTipi.ICINDEDIR:
                days = [d.strip() for d in val.split(",") if d.strip()]
                if not days:
                    raise ValueError("ICINDEDIR operatörü için en az bir gün belirtilmelidir.")
                for d in days:
                    if d not in valid_days:
                        raise ValueError(f"Geçersiz gün: '{d}'. Geçerli günler: {valid_days}")

        elif param == ParametreAdi.ISLEM_SAATI:
            if op not in [OperatorTipi.BUYUK_ESIT, OperatorTipi.KUCUK_ESIT, OperatorTipi.ESITTIR]:
                raise ValueError("islem_saati için yalnızca '>=', '<=' veya '==' operatörü desteklenir.")
            if not TIME_REGEX.match(val):
                raise ValueError("islem_saati 'HH:mm' formatında olmalıdır (örn: 09:00).")

        return self


class KosulCreate(KosulBase):
    pass


class KosulResponse(KosulBase):
    id: int
    kural_id: int
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Aksiyon Şemaları
# -------------------------------------------------------------
class AksiyonBase(BaseModel):
    aksiyon_tipi: AksiyonTipi
    aksiyon_degeri: Optional[float] = Field(None, ge=0)
    hediye_urun_id: Optional[int] = None
    kupon_sablon_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_action_fields(self):
        tip = self.aksiyon_tipi
        val = self.aksiyon_degeri

        if tip == AksiyonTipi.YUZDE_INDIRIM:
            if val is None or val <= 0 or val > 100:
                raise ValueError("YUZDE_INDIRIM için 1 ile 100 arasında bir yüzde değeri girilmelidir.")
        elif tip == AksiyonTipi.SABIT_INDIRIM:
            if val is None or val <= 0:
                raise ValueError("SABIT_INDIRIM için 0'dan büyük bir indirim tutarı girilmelidir.")
        elif tip == AksiyonTipi.HEDIYE_URUN_EKLE:
            if not self.hediye_urun_id:
                raise ValueError("HEDIYE_URUN_EKLE aksiyonu için geçerli bir hediye_urun_id seçilmelidir.")
        elif tip == AksiyonTipi.KUPON_TANIMLA:
            if not self.kupon_sablon_id:
                raise ValueError("KUPON_TANIMLA aksiyonu için geçerli bir kupon_sablon_id seçilmelidir.")
        return self


class AksiyonCreate(AksiyonBase):
    pass


class AksiyonResponse(AksiyonBase):
    id: int
    kural_id: int
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Referans Şemaları (Hediye & Kupon)
# -------------------------------------------------------------
class HediyeUrunResponse(BaseModel):
    id: int
    stok_kodu: str
    urun_adi: str
    stok_adedi: int
    durum: str
    model_config = ConfigDict(from_attributes=True)


class KuponSablonResponse(BaseModel):
    id: int
    kupon_kodu: str
    indirim_tutari: float
    kullanim_limiti: int
    durum: str
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Kural Şemaları
# -------------------------------------------------------------
class KuralCreate(BaseModel):
    ad: str = Field(..., min_length=1, max_length=255, description="Kural Adı")
    kampanya_id: Optional[int] = None
    oncelik_sirasi: Optional[int] = Field(None, ge=1, description="Öncelik sırası (Boş bırakılırsa en sona eklenir)")
    durum: KuralDurumu = Field(default=KuralDurumu.PASIF, description="Varsayılan: PASIF")
    kosullar: List[KosulCreate] = Field(..., min_length=1, description="En az bir koşul gereklidir")
    aksiyon: AksiyonCreate = Field(..., description="Uygulanacak aksiyon")


class KuralUpdate(BaseModel):
    ad: Optional[str] = Field(None, min_length=1, max_length=255)
    kampanya_id: Optional[int] = None
    oncelik_sirasi: Optional[int] = Field(None, ge=1)
    durum: Optional[KuralDurumu] = None
    kosullar: Optional[List[KosulCreate]] = None
    aksiyon: Optional[AksiyonCreate] = None


class KuralStatusUpdate(BaseModel):
    durum: KuralDurumu


class KuralPriorityUpdate(BaseModel):
    yeni_oncelik: int = Field(..., ge=1)


class KampanyaMiniResponse(BaseModel):
    id: int
    ad: str
    model_config = ConfigDict(from_attributes=True)


class KuralResponse(BaseModel):
    id: int
    ad: str
    kampanya_id: Optional[int] = None
    kampanya: Optional[KampanyaMiniResponse] = None
    oncelik_sirasi: int
    durum: KuralDurumu
    olusturulma_tarihi: datetime
    kosullar: List[KosulResponse] = []
    aksiyon: Optional[AksiyonResponse] = None
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Kampanya Şemaları
# -------------------------------------------------------------
class KampanyaCreate(BaseModel):
    ad: str = Field(..., min_length=1, max_length=255)
    aciklama: Optional[str] = None
    baslangic_tarihi: datetime
    bitis_tarihi: datetime

    @model_validator(mode="after")
    def validate_dates(self):
        if self.bitis_tarihi <= self.baslangic_tarihi:
            raise ValueError("bitis_tarihi baslangic_tarihi'nden sonra olmalıdır.")
        return self


class KampanyaResponse(BaseModel):
    id: int
    ad: str
    aciklama: Optional[str] = None
    baslangic_tarihi: datetime
    bitis_tarihi: datetime
    olusturulma_tarihi: datetime
    model_config = ConfigDict(from_attributes=True)
