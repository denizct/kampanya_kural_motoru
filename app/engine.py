"""
engine.py – Core Rule Evaluation Engine and Priority Shift Management.
"""
import logging
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.models import (
    Kural, Kosul, Aksiyon, HediyeUrun, KuponSablon,
    KuralDurumu, ParametreAdi, OperatorTipi, AksiyonTipi
)
from app.schemas import (
    SepetDegerlendirRequest, SepetDegerlendirResponse
)

logger = logging.getLogger("campaign_engine")


# -------------------------------------------------------------
# Koşul Değerlendirme Fonksiyonları
# -------------------------------------------------------------
def evaluate_condition(kosul: Kosul, context: SepetDegerlendirRequest) -> bool:
    """
    Tek bir koşulun sepet bağlamını sağlayıp sağlamadığını kontrol eder.
    """
    param = kosul.parametre
    op = kosul.operator
    val = kosul.deger.strip()

    try:
        if param == ParametreAdi.SEPET_TUTARI.value or param == "sepet_tutari":
            sepet_val = float(context.sepet_tutari)
            target_val = float(val)
            if op in [OperatorTipi.BUYUK_ESIT.value, ">="]:
                return sepet_val >= target_val
            elif op in [OperatorTipi.KUCUK_ESIT.value, "<="]:
                return sepet_val <= target_val
            elif op in [OperatorTipi.BUYUKTUR.value, ">"]:
                return sepet_val > target_val
            elif op in [OperatorTipi.KUCUKTUR.value, "<"]:
                return sepet_val < target_val
            elif op in [OperatorTipi.ESITTIR.value, "=="]:
                return sepet_val == target_val

        elif param == ParametreAdi.KULLANICI_TIPI.value or param == "kullanici_tipi":
            return context.kullanici_tipi.value.upper() == val.upper()

        elif param == ParametreAdi.ODEME_YONTEMI.value or param == "odeme_yontemi":
            return context.odeme_yontemi.value.upper() == val.upper()

        elif param == ParametreAdi.HAFTANIN_GUNU.value or param == "haftanin_gunu":
            gun = context.haftanin_gunu.value.upper()
            if op in [OperatorTipi.ESITTIR.value, "=="]:
                return gun == val.upper()
            elif op in [OperatorTipi.ICINDEDIR.value, "ICINDEDIR"]:
                allowed_days = [d.strip().upper() for d in val.split(",") if d.strip()]
                return gun in allowed_days

        elif param == ParametreAdi.ISLEM_SAATI.value or param == "islem_saati":
            context_time = context.islem_saati.strip()
            target_time = val.strip()
            if op in [OperatorTipi.BUYUK_ESIT.value, ">="]:
                return context_time >= target_time
            elif op in [OperatorTipi.KUCUK_ESIT.value, "<="]:
                return context_time <= target_time
            elif op in [OperatorTipi.ESITTIR.value, "=="]:
                return context_time == target_time

    except Exception as exc:
        logger.error(f"Koşul değerlendirme hatası (Kosul ID: {kosul.id}): {exc}")
        return False

    return False


def evaluate_rule_conditions(kural: Kural, context: SepetDegerlendirRequest) -> bool:
    """
    Kuralın tüm koşullarını mantıksal AND ile değerlendirir.
    Koşulsuz kural varsayılan olarak True döner.
    """
    if not kural.kosullar:
        return True

    for kosul in kural.kosullar:
        if not evaluate_condition(kosul, context):
            return False
    return True


# -------------------------------------------------------------
# Motor Ana Değerlendirme Fonksiyonu (Hit Policy: First)
# -------------------------------------------------------------
def evaluate_cart(db: Session, context: SepetDegerlendirRequest) -> SepetDegerlendirResponse:
    """
    Sepet bağlamını aktif kurallara göre öncelik sırasıyla tarar.
    İlk eşleşen kuralı uygular ve döngüyü sonlandırır.
    """
    # 1. Aktif kuralları öncelik sırasına göre al
    aktif_kurallar: List[Kural] = (
        db.query(Kural)
        .filter(Kural.durum == KuralDurumu.AKTIF.value)
        .order_by(asc(Kural.oncelik_sirasi))
        .all()
    )

    sepet_tutari = round(float(context.sepet_tutari), 2)

    # 2. Kuralları sırayla değerlendir
    for kural in aktif_kurallar:
        if evaluate_rule_conditions(kural, context):
            # Eşleşen İLK kural bulundu! Aksiyonu hesapla.
            aksiyon: Optional[Aksiyon] = kural.aksiyon
            if not aksiyon:
                continue

            indirim_tutari = 0.0
            ek_fayda = None
            kampanya_adi = kural.kampanya.ad if kural.kampanya else kural.ad

            if aksiyon.aksiyon_tipi == AksiyonTipi.YUZDE_INDIRIM.value:
                yuzde = float(aksiyon.aksiyon_degeri or 0)
                indirim_tutari = round(sepet_tutari * (yuzde / 100.0), 2)
                indirim_tutari = min(indirim_tutari, sepet_tutari)

            elif aksiyon.aksiyon_tipi == AksiyonTipi.SABIT_INDIRIM.value:
                sabit = float(aksiyon.aksiyon_degeri or 0)
                indirim_tutari = min(sabit, sepet_tutari)

            elif aksiyon.aksiyon_tipi == AksiyonTipi.UCRETSIZ_KARGO.value:
                indirim_tutari = 0.0
                ek_fayda = {
                    "tip": "UCRETSIZ_KARGO",
                    "aciklama": "Kargo Ücretsiz Faydası Uygulandı"
                }

            elif aksiyon.aksiyon_tipi == AksiyonTipi.HEDIYE_URUN_EKLE.value:
                indirim_tutari = 0.0
                if aksiyon.hediye_urun and aksiyon.hediye_urun.durum == "AKTIF" and aksiyon.hediye_urun.stok_adedi > 0:
                    ek_fayda = {
                        "tip": "HEDIYE_URUN",
                        "hediye_urun_id": aksiyon.hediye_urun.id,
                        "urun_adi": aksiyon.hediye_urun.urun_adi,
                        "stok_kodu": aksiyon.hediye_urun.stok_kodu,
                        "aciklama": f"Hediye Ürün Eklendi: {aksiyon.hediye_urun.urun_adi}"
                    }
                else:
                    ek_fayda = {
                        "tip": "HEDIYE_URUN_UYARI",
                        "aciklama": "Hediye ürün stokta bulunamadı."
                    }

            elif aksiyon.aksiyon_tipi == AksiyonTipi.KUPON_TANIMLA.value:
                indirim_tutari = 0.0
                if aksiyon.kupon_sablon and aksiyon.kupon_sablon.durum == "AKTIF" and aksiyon.kupon_sablon.kullanim_limiti > 0:
                    ek_fayda = {
                        "tip": "KUPON",
                        "kupon_sablon_id": aksiyon.kupon_sablon.id,
                        "kupon_kodu": aksiyon.kupon_sablon.kupon_kodu,
                        "indirim_tutari": float(aksiyon.kupon_sablon.indirim_tutari),
                        "aciklama": f"Kupon Tanımlandı: {aksiyon.kupon_sablon.kupon_kodu}"
                    }
                else:
                    ek_fayda = {
                        "tip": "KUPON_UYARI",
                        "aciklama": "Kupon şablonu geçersiz veya limiti tükenmiş."
                    }

            odenecek_tutar = round(max(0.0, sepet_tutari - indirim_tutari), 2)

            return SepetDegerlendirResponse(
                uygulanan_kural_id=kural.id,
                kampanya_adi=kampanya_adi,
                aksiyon_tipi=aksiyon.aksiyon_tipi,
                orijinal_tutar=sepet_tutari,
                indirim_tutari=indirim_tutari,
                odenecek_tutar=odenecek_tutar,
                ek_fayda=ek_fayda,
                fallback_applied=False,
                mesaj=f"'{kural.ad}' kuralı başarıyla uygulandı."
            )

    # 3. Hiçbir kural eşleşmediğinde orijinal tutarla dön
    return SepetDegerlendirResponse(
        uygulanan_kural_id=None,
        kampanya_adi=None,
        aksiyon_tipi=None,
        orijinal_tutar=sepet_tutari,
        indirim_tutari=0.0,
        odenecek_tutar=sepet_tutari,
        ek_fayda=None,
        fallback_applied=False,
        mesaj="Hiçbir kampanya kuralı eşleşmedi."
    )


def evaluate_cart_safe(db: Optional[Session], context: SepetDegerlendirRequest) -> SepetDegerlendirResponse:
    """
    Graceful Degradation / Fallback Wrapper:
    Veritabanı veya motor arızalarında sepet akışını kırmamak için
    fallback_applied=True ile sıfır indirimli güvenli yanıt üretir.
    """
    try:
        if db is None:
            raise RuntimeError("Veritabanı bağlantısı mevcut değil.")
        return evaluate_cart(db, context)
    except Exception as exc:
        logger.exception(f"Kampanya motorunda beklenmeyen hata / Fallback devreye girdi: {exc}")
        sepet_tutari = round(float(context.sepet_tutari), 2)
        return SepetDegerlendirResponse(
            uygulanan_kural_id=None,
            kampanya_adi=None,
            aksiyon_tipi=None,
            orijinal_tutar=sepet_tutari,
            indirim_tutari=0.0,
            odenecek_tutar=sepet_tutari,
            ek_fayda=None,
            fallback_applied=True,
            mesaj="Kampanya servisi geçici olarak kullanılamıyor, orijinal sepet tutarı korundu (Fallback)."
        )


# -------------------------------------------------------------
# Öncelik Kaydırma (Priority Shift & Reordering) Mantığı
# -------------------------------------------------------------
def get_next_priority(db: Session) -> int:
    """Sistemdeki en yüksek öncelik + 1 değerini döner."""
    max_priority = db.query(Kural.oncelik_sirasi).order_by(Kural.oncelik_sirasi.desc()).first()
    if max_priority and max_priority[0] is not None:
        return max_priority[0] + 1
    return 1


def reorder_on_create(db: Session, target_priority: int):
    """
    Yeni kural eklenirken: Hedef öncelik ve sonraki kuralların sırasını 1 artırır.
    Geçici negatif kaydırma ile çakışmaları önler.
    """
    rules_to_shift = (
        db.query(Kural)
        .filter(Kural.oncelik_sirasi >= target_priority)
        .order_by(Kural.oncelik_sirasi.desc())
        .all()
    )
    for r in rules_to_shift:
        r.oncelik_sirasi += 1
    db.flush()


def reorder_on_update(db: Session, rule_id: int, new_priority: int):
    """
    Mevcut bir kuralın sırası değiştiğinde aradaki kuralları kaydırır ve sıralamayı düzeltir.
    """
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        return

    old_priority = rule.oncelik_sirasi
    if old_priority == new_priority:
        return

    if new_priority < old_priority:
        # Örn: 3'ten 1'e çekildi -> 1 ve 2 olanlar +1 kayar
        affected_rules = (
            db.query(Kural)
            .filter(Kural.id != rule_id)
            .filter(Kural.oncelik_sirasi >= new_priority, Kural.oncelik_sirasi < old_priority)
            .order_by(Kural.oncelik_sirasi.desc())
            .all()
        )
        for r in affected_rules:
            r.oncelik_sirasi += 1

    else:
        # Örn: 1'den 3'e çekildi -> 2 ve 3 olanlar -1 kayar
        affected_rules = (
            db.query(Kural)
            .filter(Kural.id != rule_id)
            .filter(Kural.oncelik_sirasi > old_priority, Kural.oncelik_sirasi <= new_priority)
            .order_by(Kural.oncelik_sirasi.asc())
            .all()
        )
        for r in affected_rules:
            r.oncelik_sirasi -= 1

    rule.oncelik_sirasi = new_priority
    db.flush()
    normalize_priorities(db)


def reorder_on_delete(db: Session, deleted_priority: int):
    """
    Kural silindiğinde arkasındaki kuralların sırasını 1 azaltır.
    """
    rules_to_shift = (
        db.query(Kural)
        .filter(Kural.oncelik_sirasi > deleted_priority)
        .order_by(Kural.oncelik_sirasi.asc())
        .all()
    )
    for r in rules_to_shift:
        r.oncelik_sirasi -= 1
    db.flush()


def normalize_priorities(db: Session):
    """
    Tüm kuralların 1'den başlayan ardışık tekil sıralara sahip olmasını garanti eder.
    """
    all_rules = db.query(Kural).order_by(Kural.oncelik_sirasi.asc(), Kural.id.asc()).all()
    for idx, rule in enumerate(all_rules, start=1):
        if rule.oncelik_sirasi != idx:
            rule.oncelik_sirasi = idx
    db.flush()
