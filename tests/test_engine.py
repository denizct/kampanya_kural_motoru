"""
test_engine.py – Comprehensive automated tests covering all User Stories & Acceptance Criteria.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Kampanya, Kural, Kosul, Aksiyon, HediyeUrun, KuponSablon,
    KuralDurumu, ParametreAdi, OperatorTipi, AksiyonTipi
)
from app.seed import seed_database
from app.engine import evaluate_cart_safe
from app.schemas import SepetDegerlendirRequest, KullaniciTipi, OdemeYontemi, HaftaninGunu

# In-Memory SQLite Test Engine
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Yeni bir in-memory veritabanı oturumu sağlar ve seed verilerini yükler."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    
    # Seed verileri yükle
    # Hediyeler
    h1 = HediyeUrun(stok_kodu="HED-TERMOS", urun_adi="Paslanmaz Çelik Termos Bardak", stok_adedi=50, durum="AKTIF")
    h_out = HediyeUrun(stok_kodu="HED-BITIK", urun_adi="Tükenmiş Hediye", stok_adedi=0, durum="PASIF")
    # Kuponlar
    k1 = KuponSablon(kupon_kodu="KUPON100", indirim_tutari=100.0, kullanim_limiti=50, durum="AKTIF")
    k_out = KuponSablon(kupon_kodu="KUPONBITTI", indirim_tutari=50.0, kullanim_limiti=0, durum="PASIF")
    db.add_all([h1, h_out, k1, k_out])
    db.flush()

    # Kural 1: Hafta Sonu 500 TL Üzerine %10 İndirim
    kural1 = Kural(ad="Hafta Sonu 500 TL Üzerine %10 İndirim", oncelik_sirasi=1, durum=KuralDurumu.AKTIF.value)
    db.add(kural1)
    db.flush()
    db.add(Kosul(kural_id=kural1.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="500"))
    db.add(Kosul(kural_id=kural1.id, parametre=ParametreAdi.HAFTANIN_GUNU.value, operator=OperatorTipi.ICINDEDIR.value, deger="CUMARTESI,PAZAR"))
    db.add(Aksiyon(kural_id=kural1.id, aksiyon_tipi=AksiyonTipi.YUZDE_INDIRIM.value, aksiyon_degeri=10.0))

    # Kural 2: 400 TL Üzeri Ücretsiz Kargo
    kural2 = Kural(ad="400 TL Üzerine Ücretsiz Kargo", oncelik_sirasi=2, durum=KuralDurumu.AKTIF.value)
    db.add(kural2)
    db.flush()
    db.add(Kosul(kural_id=kural2.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="400"))
    db.add(Aksiyon(kural_id=kural2.id, aksiyon_tipi=AksiyonTipi.UCRETSIZ_KARGO.value))

    # Kural 3: VIP Müşterilere 1000 TL Üzeri 150 TL İndirim
    kural3 = Kural(ad="VIP 1000 TL Üzeri 150 TL İndirim", oncelik_sirasi=3, durum=KuralDurumu.AKTIF.value)
    db.add(kural3)
    db.flush()
    db.add(Kosul(kural_id=kural3.id, parametre=ParametreAdi.KULLANICI_TIPI.value, operator=OperatorTipi.ESITTIR.value, deger="VIP"))
    db.add(Kosul(kural_id=kural3.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="1000"))
    db.add(Aksiyon(kural_id=kural3.id, aksiyon_tipi=AksiyonTipi.SABIT_INDIRIM.value, aksiyon_degeri=150.0))

    # Kural 4: Hediye Termos Kuralı
    kural4 = Kural(ad="750 TL Üzeri Kredi Kartına Hediye Termos", oncelik_sirasi=4, durum=KuralDurumu.AKTIF.value)
    db.add(kural4)
    db.flush()
    db.add(Kosul(kural_id=kural4.id, parametre=ParametreAdi.SEPET_TUTARI.value, operator=OperatorTipi.BUYUK_ESIT.value, deger="750"))
    db.add(Kosul(kural_id=kural4.id, parametre=ParametreAdi.ODEME_YONTEMI.value, operator=OperatorTipi.ESITTIR.value, deger="KREDI_KARTI"))
    db.add(Aksiyon(kural_id=kural4.id, aksiyon_tipi=AksiyonTipi.HEDIYE_URUN_EKLE.value, hediye_urun_id=h1.id))

    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# -------------------------------------------------------------
# 1. Hit Policy: First & Koşul Değerlendirme Testleri
# -------------------------------------------------------------
def test_evaluation_happy_path_percentage_discount(client):
    """Senaryo: Hafta Sonu 600 TL sepete %10 indirim uygulanıp 540 TL dönmelidir."""
    payload = {
        "sepet_tutari": 600.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "PAZAR",
        "odeme_yontemi": "KREDI_KARTI"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["uygulanan_kural_id"] is not None
    assert data["aksiyon_tipi"] == "YUZDE_INDIRIM"
    assert data["orijinal_tutar"] == 600.0
    assert data["indirim_tutari"] == 60.0
    assert data["odenecek_tutar"] == 540.0
    assert data["fallback_applied"] is False


def test_evaluation_hit_policy_first_priority_winning(client):
    """
    Senaryo: 600 TL Pazar günü sepetine hem Öncelik 1 (%10) hem Öncelik 2 (Kargo Bedava) uyar.
    Yalnızca Öncelik 1 çalışmalı, Öncelik 2 elenmelidir.
    """
    payload = {
        "sepet_tutari": 600.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "PAZAR",
        "odeme_yontemi": "KREDI_KARTI"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["aksiyon_tipi"] == "YUZDE_INDIRIM"
    assert data["indirim_tutari"] == 60.0


def test_evaluation_lower_priority_executes_when_first_not_matched(client):
    """
    Senaryo: Hafta içi (SALI) 450 TL sepet, Kural 1'e uymaz (Pazar değil),
    fakat Kural 2'ye (>= 400 TL) uyar. Kural 2 (Ücretsiz Kargo) çalışmalıdır.
    """
    payload = {
        "sepet_tutari": 450.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "SALI",
        "odeme_yontemi": "HAVALE"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["aksiyon_tipi"] == "UCRETSIZ_KARGO"
    assert data["indirim_tutari"] == 0.0
    assert data["odenecek_tutar"] == 450.0
    assert data["ek_fayda"]["tip"] == "UCRETSIZ_KARGO"


def test_evaluation_no_match_returns_zero_discount(client):
    """Senaryo: Hiçbir kural uymadığında 200 OK ile 0 TL indirim dönmelidir."""
    payload = {
        "sepet_tutari": 100.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "SALI",
        "odeme_yontemi": "HAVALE"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["uygulanan_kural_id"] is None
    assert data["indirim_tutari"] == 0.0
    assert data["odenecek_tutar"] == 100.0
    assert data["ek_fayda"] is None


def test_evaluation_gift_product_benefit(client):
    """Senaryo: Hediye kuralı eşleştiğinde ek_fayda içinde ürün bilgisi dönmelidir."""
    payload = {
        "sepet_tutari": 800.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "CARSAMBA",
        "odeme_yontemi": "KREDI_KARTI"
    }
    # Hafta sonu değil, Kural 1 uymuyor. Kural 2 uyar (400 TL).
    # Kural 2'yi pasife alalım ki Kural 4'e gelsin:
    client.patch("/api/v1/kurallar/2/durum", json={"durum": "PASIF"})

    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["aksiyon_tipi"] == "HEDIYE_URUN_EKLE"
    assert data["ek_fayda"] is not None
    assert data["ek_fayda"]["tip"] == "HEDIYE_URUN"
    assert data["ek_fayda"]["stok_kodu"] == "HED-TERMOS"


# -------------------------------------------------------------
# 2. Validation & Graceful Fallback Testleri
# -------------------------------------------------------------
def test_evaluation_validation_error_negative_cart(client):
    """Senaryo: Negatif sepet tutarında 400 Bad Request dönmelidir."""
    payload = {
        "sepet_tutari": -50.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "PAZAR",
        "odeme_yontemi": "KREDI_KARTI"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_evaluation_validation_error_invalid_enum(client):
    """Senaryo: Tanımsız enum değerinde (BITCOIN) 400 Bad Request dönmelidir."""
    payload = {
        "sepet_tutari": 200.0,
        "kullanici_tipi": "STANDART",
        "islem_saati": "14:30",
        "haftanin_gunu": "PAZAR",
        "odeme_yontemi": "BITCOIN"
    }
    response = client.post("/api/v1/kampanya/degerlendir", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_graceful_fallback_on_db_error():
    """Senaryo: Veritabanı veya motor arızasında fallback_applied=true ile 0 TL indirim dönmelidir."""
    req = SepetDegerlendirRequest(
        sepet_tutari=750.0,
        kullanici_tipi=KullaniciTipi.STANDART,
        islem_saati="14:30",
        haftanin_gunu=HaftaninGunu.CUMARTESI,
        odeme_yontemi=OdemeYontemi.KREDI_KARTI
    )
    # db = None ile simüle ediyoruz
    res = evaluate_cart_safe(db=None, context=req)
    assert res.fallback_applied is True
    assert res.indirim_tutari == 0.0
    assert res.odenecek_tutar == 750.0
    assert res.uygulanan_kural_id is None


# -------------------------------------------------------------
# 3. Kural Oluşturma, Durum Değiştirme & Öncelik Kaydırma (Shift Logic)
# -------------------------------------------------------------
def test_create_rule_defaults_to_pasif(client):
    """Senaryo: Yeni kural varsayılan olarak PASIF olarak kaydedilmelidir."""
    payload = {
        "ad": "Yeni Sezon İndirimi",
        "kosullar": [
            {"parametre": "sepet_tutari", "operator": ">=", "deger": "300"}
        ],
        "aksiyon": {
            "aksiyon_tipi": "SABIT_INDIRIM",
            "aksiyon_degeri": 30.0
        }
    }
    response = client.post("/api/v1/kurallar", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["durum"] == "PASIF"
    assert data["id"] is not None


def test_create_rule_with_out_of_stock_gift_rejected(client):
    """Senaryo: Stoğu tükenmiş hediye ürün seçildiğinde 400 uyarısı dönmelidir."""
    payload = {
        "ad": "Tükenmiş Hediye Kuralı",
        "kosullar": [
            {"parametre": "sepet_tutari", "operator": ">=", "deger": "500"}
        ],
        "aksiyon": {
            "aksiyon_tipi": "HEDIYE_URUN_EKLE",
            "hediye_urun_id": 2  # HED-BITIK (stok 0, pasif)
        }
    }
    response = client.post("/api/v1/kurallar", json=payload)
    assert response.status_code == 400
    assert "stokta bulunmamaktadır" in response.json()["detail"]


def test_priority_shift_logic(client):
    """
    Senaryo:
    1. Araya 2. sıraya yeni kural eklendiğinde, mevcut 2, 3, 4 -> 3, 4, 5 olmalıdır.
    2. 4. sıradaki kural 1'e çekildiğinde aradaki kurallar kaymalıdır.
    """
    # 1. 2. sıraya kural ekle
    payload = {
        "ad": "Araya Eklenen Kural (Sıra 2)",
        "oncelik_sirasi": 2,
        "kosullar": [{"parametre": "sepet_tutari", "operator": ">=", "deger": "200"}],
        "aksiyon": {"aksiyon_tipi": "SABIT_INDIRIM", "aksiyon_degeri": 20.0}
    }
    res = client.post("/api/v1/kurallar", json=payload)
    assert res.status_code == 201

    rules = client.get("/api/v1/kurallar").json()
    priorities = [r["oncelik_sirasi"] for r in rules]
    assert priorities == [1, 2, 3, 4, 5]

    # 2. 3. sıradaki kuralın sırasını 1 yap (reorder)
    rule_3_id = rules[2]["id"]
    shift_res = client.patch(f"/api/v1/kurallar/{rule_3_id}/oncelik", json={"yeni_oncelik": 1})
    assert shift_res.status_code == 200

    updated_rules = client.get("/api/v1/kurallar").json()
    updated_priorities = [r["oncelik_sirasi"] for r in updated_rules]
    assert updated_priorities == [1, 2, 3, 4, 5]
    assert updated_rules[0]["id"] == rule_3_id
