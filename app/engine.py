"""
engine.py – Kural Değerlendirme Motoru (Rule Engine Core)

Hit Policy: FIRST (F)
- Kurallar oncelik_sirasi ASC sırayla işlenir.
- Tüm koşulları (AND mantığıyla) sağlayan ilk kural seçilir.
- Aksiyonu hesaplanır, döngü kırılır.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, joinedload

from app.models import AksiyonTipi, Kural, KuralDurumu, Operator, Parametre
from app.schemas import DegerlendirmeResponse, DegerlendirilecekSepet, EkFayda

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")
KARGO_UCRETI = Decimal("29.90")  # Varsayılan kargo ücreti tasarrufu


# ── Koşul Değerlendirici ──────────────────────────────────────────────────────

def _deger_al(sepet: DegerlendirilecekSepet, parametre: Parametre) -> str | Decimal | None:
    """Sepetten ilgili parametreyi çeker."""
    mapping = {
        Parametre.SEPET_TUTARI: sepet.sepet_tutari,
        Parametre.KULLANICI_TIPI: sepet.kullanici_tipi,
        Parametre.ISLEM_SAATI: sepet.islem_saati,
        Parametre.HAFTANIN_GUNU: sepet.haftanin_gunu,
        Parametre.ODEME_YONTEMI: sepet.odeme_yontemi,
    }
    return mapping.get(parametre)


def _saate_dakika_donustur(saat_str: str) -> int:
    """'HH:MM' formatını dakikaya çevirir."""
    try:
        h, m = saat_str.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


def _kosul_saglandi_mi(gercek_deger: str | Decimal | None, operator: Operator, beklenen: str) -> bool:
    """
    Tek bir koşulu değerlendirir.

    Güvenlik notları:
    - gercek_deger None ise → False (sepette bu parametre yoktu).
    - Tip dönüşümü başarısız olursa → False (exception yukarıdaki
      _kural_eslesti_mi'nin try/except'ine iletilir, motor durmuyor).
    - ICINDEDIR: boş/geçersiz token'lar (virgül artıkları, boşluklar)
      sessizce filtrelenir; "merhaba" gibi gün olmayan değerler eşleşmez.
    """
    if gercek_deger is None:
        return False

    # Sayısal karşılaştırmalar
    if operator in (Operator.BUYUKTUR, Operator.KUCUKTUR, Operator.BUYUK_ESIT, Operator.KUCUK_ESIT):
        try:
            gercek = Decimal(str(gercek_deger))
            beklenen_decimal = Decimal(beklenen)
        except Exception:
            # Saat karşılaştırması (HH:MM formatı)
            try:
                gercek = _saate_dakika_donustur(str(gercek_deger))
                beklenen_decimal = _saate_dakika_donustur(beklenen)
            except Exception:
                return False

        ops = {
            Operator.BUYUKTUR: gercek > beklenen_decimal,
            Operator.KUCUKTUR: gercek < beklenen_decimal,
            Operator.BUYUK_ESIT: gercek >= beklenen_decimal,
            Operator.KUCUK_ESIT: gercek <= beklenen_decimal,
        }
        return ops.get(operator, False)

    # Eşitlik karşılaştırması
    if operator == Operator.ESITTIR:
        return str(gercek_deger).upper() == beklenen.upper()

    # İçindedir (CSV liste)
    # Boş token'lar ve sadece boşluktan oluşan girişler filtrelenir.
    # "MERHABA" veya "5" gibi geçersiz gün isimleri listede yer almaz → False döner.
    if operator == Operator.ICINDEDIR:
        degerler = [d.strip().upper() for d in beklenen.split(",") if d.strip()]
        if not degerler:
            return False  # Tamamen boş liste – kural geçersiz, eşleşme yok
        return str(gercek_deger).upper() in degerler

    return False


def _kural_eslesti_mi(kural: Kural, sepet: DegerlendirilecekSepet) -> bool:
    """
    Bir kuralın tüm koşullarını AND mantığıyla kontrol eder.

    Güvenlik: Her koşul kendi try/except bloğunda çalışır.
    Tip uyuşmazlığı veya beklenmedik hata durumunda o koşul False
    kabul edilir; motor FALLBACK'e düşmez, sıradaki kurala geçer.
    """
    if not kural.kosullar:
        return False
    for kosul in kural.kosullar:
        try:
            gercek = _deger_al(sepet, kosul.parametre)
            sonuc = _kosul_saglandi_mi(gercek, kosul.operator, kosul.deger)
        except Exception as exc:
            logger.warning(
                "Koşul değerlendirme hatası (kural_id=%s, parametre=%s): %s – False kabul edildi.",
                kural.id, kosul.parametre, exc,
            )
            sonuc = False
        if not sonuc:
            return False
    return True


# ── Aksiyon Hesaplayıcı ───────────────────────────────────────────────────────

def _aksiyon_hesapla(
    aksiyon_tipi: AksiyonTipi,
    aksiyon_degeri: Decimal,
    orijinal_tutar: Decimal,
    hediye_urun_adi: str | None,
    kupon_kodu: str | None,
    kupon_indirimi: Decimal | None,
) -> tuple[Decimal, Decimal, EkFayda | None]:
    """
    Returns: (indirim_tutari, odenecek_tutar, ek_fayda)
    """
    indirim = Decimal("0")
    ek_fayda: EkFayda | None = None

    if aksiyon_tipi == AksiyonTipi.YUZDE_INDIRIM:
        indirim = (orijinal_tutar * aksiyon_degeri / 100).quantize(TWO_PLACES, ROUND_HALF_UP)
        ek_fayda = EkFayda(tip="YUZDE_INDIRIM", detay=f"%{aksiyon_degeri} indirim uygulandı.")

    elif aksiyon_tipi == AksiyonTipi.SABIT_INDIRIM:
        indirim = aksiyon_degeri.quantize(TWO_PLACES, ROUND_HALF_UP)
        ek_fayda = EkFayda(tip="SABIT_INDIRIM", detay=f"{indirim} TL sabit indirim uygulandı.")

    elif aksiyon_tipi == AksiyonTipi.UCRETSIZ_KARGO:
        indirim = KARGO_UCRETI
        ek_fayda = EkFayda(tip="UCRETSIZ_KARGO", detay=f"Ücretsiz kargo sağlandı ({KARGO_UCRETI} TL tasarruf).")

    elif aksiyon_tipi == AksiyonTipi.HEDIYE_URUN_EKLE:
        indirim = Decimal("0")
        ad = hediye_urun_adi or "Hediye Ürün"
        ek_fayda = EkFayda(tip="HEDIYE_URUN", detay=f"'{ad}' siparişinize hediye eklendi.")

    elif aksiyon_tipi == AksiyonTipi.KUPON_TANIMLA:
        indirim = Decimal("0")
        kod = kupon_kodu or "KUPON"
        ind = kupon_indirimi or Decimal("0")
        ek_fayda = EkFayda(
            tip="KUPON",
            detay=f"'{kod}' kuponu tanımlandı. Sonraki alışverişinizde {ind} TL indirim.",
        )

    odenecek = max(Decimal("0"), orijinal_tutar - indirim).quantize(TWO_PLACES, ROUND_HALF_UP)
    return indirim.quantize(TWO_PLACES, ROUND_HALF_UP), odenecek, ek_fayda


# ── Ana Motor Fonksiyonu ──────────────────────────────────────────────────────

def kampanya_degerlendir(
    sepet: DegerlendirilecekSepet,
    db: Session,
) -> DegerlendirmeResponse:
    """
    İstekteki sepeti aktif kurallar üzerinde değerlendirir.
    Hit Policy: FIRST – ilk eşleşen kuralı uygular.
    """
    orijinal_tutar = sepet.sepet_tutari.quantize(TWO_PLACES, ROUND_HALF_UP)

    try:
        # Aktif kuralları öncelik sırasıyla getir (eager load)
        kurallar = (
            db.query(Kural)
            .options(
                joinedload(Kural.kosullar),
                joinedload(Kural.aksiyon).joinedload("hediye_urun"),
                joinedload(Kural.aksiyon).joinedload("kupon_sablonu"),
                joinedload(Kural.kampanya),
            )
            .filter(Kural.durum == KuralDurumu.AKTIF)
            .order_by(Kural.oncelik_sirasi.asc())
            .all()
        )

        for kural in kurallar:
            if _kural_eslesti_mi(kural, sepet):
                aksiyon = kural.aksiyon
                if not aksiyon:
                    continue

                hediye_adi = aksiyon.hediye_urun.urun_adi if aksiyon.hediye_urun else None
                kupon_kodu = aksiyon.kupon_sablonu.kupon_kodu if aksiyon.kupon_sablonu else None
                kupon_ind = aksiyon.kupon_sablonu.indirim_tutari if aksiyon.kupon_sablonu else None

                indirim, odenecek, ek_fayda = _aksiyon_hesapla(
                    aksiyon.aksiyon_tipi,
                    Decimal(str(aksiyon.aksiyon_degeri)),
                    orijinal_tutar,
                    hediye_adi,
                    kupon_kodu,
                    kupon_ind,
                )

                kampanya_adi = kural.kampanya.ad if kural.kampanya else None

                return DegerlendirmeResponse(
                    durum="ESLESTI",
                    uygulanan_kural_id=kural.id,
                    kampanya_adi=kampanya_adi,
                    aksiyon_tipi=aksiyon.aksiyon_tipi.value,
                    orijinal_tutar=orijinal_tutar,
                    indirim_tutari=indirim,
                    odenecek_tutar=odenecek,
                    ek_fayda=ek_fayda,
                    fallback_applied=False,
                    mesaj=f"'{kural.ad}' kuralı uygulandı.",
                )

        # Hiçbir kural eşleşmedi
        return DegerlendirmeResponse(
            durum="ESLESMEDI",
            orijinal_tutar=orijinal_tutar,
            indirim_tutari=Decimal("0.00"),
            odenecek_tutar=orijinal_tutar,
            fallback_applied=False,
            mesaj="Geçerli kampanya kuralı bulunamadı.",
        )

    except Exception as exc:
        logger.exception("Kural motoru beklenmedik hata: %s", exc)
        # Güvenli fallback – sepeti koru
        return DegerlendirmeResponse(
            durum="FALLBACK",
            orijinal_tutar=orijinal_tutar,
            indirim_tutari=Decimal("0.00"),
            odenecek_tutar=orijinal_tutar,
            fallback_applied=True,
            mesaj="Motor hatası nedeniyle orijinal tutar korundu.",
        )
