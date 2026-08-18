"""
seed.py – Initial data seeder for test campaigns, rules, conditions, actions, gift items, and coupons.
"""
from datetime import datetime, timedelta
from app.database import SessionLocal, init_db
from app.models import (
    Kampanya, Kural, Kosul, Aksiyon, HediyeUrun, KuponSablon,
    KuralDurumu, ParametreAdi, OperatorTipi, AksiyonTipi
)


def seed_database():
    """Veritabanını örnek başlangıç verileriyle doldurur."""
    init_db()
    db = SessionLocal()

    try:
        # Eğer zaten veriler varsa tekrar ekleme
        if db.query(Kural).first():
            print("Veritabanı zaten dolu, seed adımı atlandı.")
            return

        print("Veritabanı seed işlemi başlatılıyor...")

        # 1. Hediye Ürünler
        hediye1 = HediyeUrun(stok_kodu="HED-TERMOS", urun_adi="Paslanmaz Çelik Termos Bardak", stok_adedi=50, durum="AKTIF")
        hediye2 = HediyeUrun(stok_kodu="HED-CANTA", urun_adi="Organik Bez Alışveriş Çantası", stok_adedi=120, durum="AKTIF")
        hediye3 = HediyeUrun(stok_kodu="HED-KULAKLIK", urun_adi="Kablosuz Bluetooth Kulaklık", stok_adedi=0, durum="PASIF")
        db.add_all([hediye1, hediye2, hediye3])
        db.flush()

        # 2. Kupon Şablonları
        kupon1 = KuponSablon(kupon_kodu="KUPON100", indirim_tutari=100.0, kullanim_limiti=50, durum="AKTIF")
        kupon2 = KuponSablon(kupon_kodu="KUPON50", indirim_tutari=50.0, kullanim_limiti=200, durum="AKTIF")
        kupon3 = KuponSablon(kupon_kodu="KUPONBITTI", indirim_tutari=25.0, kullanim_limiti=0, durum="PASIF")
        db.add_all([kupon1, kupon2, kupon3])
        db.flush()

        # 3. Kampanyalar
        kampanya1 = Kampanya(
            ad="Hafta Sonu & Bahar Festivali",
            aciklama="Hafta sonuna özel sepet ve kategori indirimleri",
            baslangic_tarihi=datetime.utcnow() - timedelta(days=1),
            bitis_tarihi=datetime.utcnow() + timedelta(days=60)
        )
        kampanya2 = Kampanya(
            ad="VIP Sadakat ve Gece Fırsatları",
            aciklama="Sadık müşterilere ve gece alışverişlerine özel avantajlar",
            baslangic_tarihi=datetime.utcnow() - timedelta(days=1),
            bitis_tarihi=datetime.utcnow() + timedelta(days=90)
        )
        db.add_all([kampanya1, kampanya2])
        db.flush()

        # 4. Kurallar, Koşullar ve Aksiyonlar
        # Kural 1: Hafta Sonu 500 TL Üzerine %10 İndirim
        kural1 = Kural(
            kampanya_id=kampanya1.id,
            ad="Hafta Sonu 500 TL Üzerine %10 İndirim",
            oncelik_sirasi=1,
            durum=KuralDurumu.AKTIF.value
        )
        db.add(kural1)
        db.flush()

        k1_c1 = Kosul(kural_id=kural1.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="500")
        k1_c2 = Kosul(kural_id=kural1.id, parametre=ParametreAdi.HAFTANIN_GUNU.value, operator=OperatorTipi.ICINDEDIR.value, deger="CUMARTESI,PAZAR")
        k1_a1 = Aksiyon(kural_id=kural1.id, aksiyon_tipi=AksiyonTipi.YUZDE_INDIRIM.value, aksiyon_degeri=10.0)
        db.add_all([k1_c1, k1_c2, k1_a1])

        # Kural 2: VIP Müşterilere 1000 TL Üzeri 150 TL İndirim
        kural2 = Kural(
            kampanya_id=kampanya2.id,
            ad="VIP Müşterilere 1000 TL Üzeri 150 TL İndirim",
            oncelik_sirasi=2,
            durum=KuralDurumu.AKTIF.value
        )
        db.add(kural2)
        db.flush()

        k2_c1 = Kosul(kural_id=kural2.id, parametre=ParametreAdi.KULLANICI_TIPI.value, operator=OperatorTipi.ESITTIR.value, deger="VIP")
        k2_c2 = Kosul(kural_id=kural2.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="1000")
        k2_a1 = Aksiyon(kural_id=kural2.id, aksiyon_tipi=AksiyonTipi.SABIT_INDIRIM.value, aksiyon_degeri=150.0)
        db.add_all([k2_c1, k2_c2, k2_a1])

        # Kural 3: Gece Alışverişine Ücretsiz Kargo
        kural3 = Kural(
            kampanya_id=kampanya2.id,
            ad="Gece Alışverişine Ücretsiz Kargo",
            oncelik_sirasi=3,
            durum=KuralDurumu.AKTIF.value
        )
        db.add(kural3)
        db.flush()

        k3_c1 = Kosul(kural_id=kural3.id, parametre=ParametreAdi.ISLEM_SAATI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="22:00")
        k3_a1 = Aksiyon(kural_id=kural3.id, aksiyon_tipi=AksiyonTipi.UCRETSIZ_KARGO.value)
        db.add_all([k3_c1, k3_a1])

        # Kural 4: 750 TL Üzeri Kredi Kartı Alışverişine Hediye Termos
        kural4 = Kural(
            kampanya_id=kampanya1.id,
            ad="750 TL Üzeri Kredi Kartına Hediye Termos",
            oncelik_sirasi=4,
            durum=KuralDurumu.AKTIF.value
        )
        db.add(kural4)
        db.flush()

        k4_c1 = Kosul(kural_id=kural4.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="750")
        k4_c2 = Kosul(kural_id=kural4.id, parametre=ParametreAdi.ODEME_YONTEMI.value, operator=OperatorTipi.ESITTIR.value, deger="KREDI_KARTI")
        k4_a1 = Aksiyon(kural_id=kural4.id, aksiyon_tipi=AksiyonTipi.HEDIYE_URUN_EKLE.value, hediye_urun_id=hediye1.id)
        db.add_all([k4_c1, k4_c2, k4_a1])

        # Kural 5: Yeni Üyelere Hoş Geldin Kuponu (Pasif)
        kural5 = Kural(
            kampanya_id=kampanya1.id,
            ad="Yeni Üyelere Hoş Geldin Kuponu",
            oncelik_sirasi=5,
            durum=KuralDurumu.PASIF.value
        )
        db.add(kural5)
        db.flush()

        k5_c1 = Kosul(kural_id=kural5.id, parametre=ParametreAdi.KULLANICI_TIPI.value, operator=OperatorTipi.ESITTIR.value, deger="YENI")
        k5_c2 = Kosul(kural_id=kural5.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="300")
        k5_a1 = Aksiyon(kural_id=kural5.id, aksiyon_tipi=AksiyonTipi.KUPON_TANIMLA.value, kupon_sablon_id=kupon2.id)
        db.add_all([k5_c1, k5_c2, k5_a1])

        db.commit()
        print("Seed verileri başarıyla yüklendi!")

    except Exception as exc:
        db.rollback()
        print(f"Seed işlemi sırasında hata oluştu: {exc}")
        raise exc
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
