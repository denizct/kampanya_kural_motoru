"""
seed.py – Veritabanı başlangıç verilerini oluşturur (idempotent).
Konteyner ayağa kalktığında otomatik çalışır.
"""
import logging
import time
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import SessionLocal, engine
from app.models import (
    AksiyonTipi,
    Base,
    HediyeUrun,
    Kampanya,
    KuralDurumu,
    KuponSablonu,
    Operator,
    Parametre,
    Aksiyon,
    Kosul,
    Kural,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def bekle_ve_baglan(max_deneme: int = 15, bekleme_suresi: float = 3.0):
    """PostgreSQL hazır olana kadar bekler."""
    for deneme in range(1, max_deneme + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Veritabanı bağlantısı kuruldu.")
            return
        except OperationalError:
            logger.warning(f"⏳ Veritabanı bekleniyor... ({deneme}/{max_deneme})")
            time.sleep(bekleme_suresi)
    raise RuntimeError("❌ Veritabanına bağlanılamadı!")


def seed():
    bekle_ve_baglan()
    Base.metadata.create_all(bind=engine)
    logger.info("📦 Tablolar oluşturuldu / kontrol edildi.")

    db = SessionLocal()
    try:
        # İdempotent kontrol
        if db.query(Kampanya).count() > 0:
            logger.info("ℹ️  Seed verisi zaten mevcut, atlanıyor.")
            return

        # ── Hediye Ürünler ────────────────────────────────────────────────────
        hediye1 = HediyeUrun(
            stok_kodu="HEDIYE-001",
            urun_adi="Premium Kol Saati",
            stok_adedi=50,
            durum="AKTIF",
        )
        hediye2 = HediyeUrun(
            stok_kodu="HEDIYE-002",
            urun_adi="Deri Cüzdan",
            stok_adedi=100,
            durum="AKTIF",
        )
        db.add_all([hediye1, hediye2])
        db.flush()

        # ── Kupon Şablonları ──────────────────────────────────────────────────
        kupon1 = KuponSablonu(
            kupon_kodu="VIPINDIRIM50",
            indirim_tutari=Decimal("50.00"),
            kullanim_limiti=1,
            durum="AKTIF",
        )
        kupon2 = KuponSablonu(
            kupon_kodu="HAFTSONU25",
            indirim_tutari=Decimal("25.00"),
            kullanim_limiti=3,
            durum="AKTIF",
        )
        db.add_all([kupon1, kupon2])
        db.flush()

        # ── Kampanyalar ───────────────────────────────────────────────────────
        kampanya1 = Kampanya(
            ad="VIP Yaz Kampanyası 2024",
            aciklama="VIP müşterilere özel yüksek sepet tutarlarında indirim kampanyası.",
        )
        kampanya2 = Kampanya(
            ad="Hafta Sonu Fırsatları",
            aciklama="Cumartesi ve Pazar günleri geçerli kampanya paketi.",
        )
        db.add_all([kampanya1, kampanya2])
        db.flush()

        # ── Kurallar & Koşullar & Aksiyonlar ──────────────────────────────────

        # Kural 1 – Öncelik 1: VIP + 1000 TL üzeri → %20 indirim
        kural1 = Kural(
            kampanya_id=kampanya1.id,
            ad="VIP Büyük Sepet %20 İndirim",
            oncelik_sirasi=1,
            durum=KuralDurumu.AKTIF,
        )
        db.add(kural1)
        db.flush()
        db.add_all([
            Kosul(kural_id=kural1.id, parametre=Parametre.KULLANICI_TIPI, operator=Operator.ESITTIR, deger="VIP"),
            Kosul(kural_id=kural1.id, parametre=Parametre.SEPET_TUTARI, operator=Operator.BUYUK_ESIT, deger="1000"),
        ])
        db.add(Aksiyon(kural_id=kural1.id, aksiyon_tipi=AksiyonTipi.YUZDE_INDIRIM, aksiyon_degeri=Decimal("20")))

        # Kural 2 – Öncelik 2: VIP + 500–999 TL → %10 indirim
        kural2 = Kural(
            kampanya_id=kampanya1.id,
            ad="VIP Orta Sepet %10 İndirim",
            oncelik_sirasi=2,
            durum=KuralDurumu.AKTIF,
        )
        db.add(kural2)
        db.flush()
        db.add_all([
            Kosul(kural_id=kural2.id, parametre=Parametre.KULLANICI_TIPI, operator=Operator.ESITTIR, deger="VIP"),
            Kosul(kural_id=kural2.id, parametre=Parametre.SEPET_TUTARI, operator=Operator.BUYUK_ESIT, deger="500"),
            Kosul(kural_id=kural2.id, parametre=Parametre.SEPET_TUTARI, operator=Operator.KUCUK_ESIT, deger="999"),
        ])
        db.add(Aksiyon(kural_id=kural2.id, aksiyon_tipi=AksiyonTipi.YUZDE_INDIRIM, aksiyon_degeri=Decimal("10")))

        # Kural 3 – Öncelik 3: Hafta sonu + Kredi Kartı → Ücretsiz kargo
        kural3 = Kural(
            kampanya_id=kampanya2.id,
            ad="Hafta Sonu Kredi Kartı Ücretsiz Kargo",
            oncelik_sirasi=3,
            durum=KuralDurumu.AKTIF,
        )
        db.add(kural3)
        db.flush()
        db.add_all([
            Kosul(kural_id=kural3.id, parametre=Parametre.HAFTANIN_GUNU, operator=Operator.ICINDEDIR, deger="CUMARTESI,PAZAR"),
            Kosul(kural_id=kural3.id, parametre=Parametre.ODEME_YONTEMI, operator=Operator.ESITTIR, deger="KREDI_KARTI"),
        ])
        db.add(Aksiyon(kural_id=kural3.id, aksiyon_tipi=AksiyonTipi.UCRETSIZ_KARGO, aksiyon_degeri=Decimal("0")))

        # Kural 4 – Öncelik 4: 200 TL üzeri, öğleden sonra → Hediye ürün
        kural4 = Kural(
            kampanya_id=kampanya2.id,
            ad="Öğleden Sonra Alışveriş Hediyesi",
            oncelik_sirasi=4,
            durum=KuralDurumu.AKTIF,
        )
        db.add(kural4)
        db.flush()
        db.add_all([
            Kosul(kural_id=kural4.id, parametre=Parametre.SEPET_TUTARI, operator=Operator.BUYUK_ESIT, deger="200"),
            Kosul(kural_id=kural4.id, parametre=Parametre.ISLEM_SAATI, operator=Operator.BUYUK_ESIT, deger="12:00"),
            Kosul(kural_id=kural4.id, parametre=Parametre.ISLEM_SAATI, operator=Operator.KUCUK_ESIT, deger="18:00"),
        ])
        db.add(Aksiyon(
            kural_id=kural4.id,
            aksiyon_tipi=AksiyonTipi.HEDIYE_URUN_EKLE,
            aksiyon_degeri=Decimal("0"),
            hediye_urun_id=hediye2.id,
        ))

        db.commit()
        logger.info("✅ Seed verisi başarıyla yüklendi.")

    except Exception as e:
        db.rollback()
        logger.exception("❌ Seed hatası: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
