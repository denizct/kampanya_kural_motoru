"""
main.py – FastAPI Application, API v1 endpoints, custom error handlers, and template mounting.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.database import get_db, init_db, SessionLocal
from app.models import (
    Kampanya, Kural, Kosul, Aksiyon, HediyeUrun, KuponSablon,
    KuralDurumu, ParametreAdi, OperatorTipi, AksiyonTipi
)
from app.schemas import (
    SepetDegerlendirRequest, SepetDegerlendirResponse, ErrorResponse,
    KuralCreate, KuralUpdate, KuralResponse, KuralStatusUpdate, KuralPriorityUpdate,
    KampanyaCreate, KampanyaResponse,
    HediyeUrunResponse, KuponSablonResponse
)
from app.engine import (
    evaluate_cart_safe, get_next_priority, reorder_on_create,
    reorder_on_update, reorder_on_delete, normalize_priorities
)
from app.seed import seed_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Tabloları oluştur ve gerekiyorsa seed et
    try:
        init_db()
        seed_database()
    except Exception as exc:
        logger.warning(f"Startup DB init/seed warning: {exc}")
    yield


app = FastAPI(
    title="Kampanya Kural Motoru API",
    description="E-Ticaret sepet indirimleri ve kural yönetim motoru REST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statik ve Şablon Dizinleri
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
templates_dir = os.path.join(BASE_DIR, "templates")

if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


# -------------------------------------------------------------
# Standart Hata İşleyicileri (Error Handlers)
# -------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic doğrulama hatalarını 400 Bad Request ve standart şema ile döner."""
    error_details = []
    for err in exc.errors():
        field = " -> ".join([str(loc) for loc in err.get("loc", [])])
        error_details.append({
            "field": field,
            "message": err.get("msg"),
            "type": err.get("type")
        })

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Geçersiz veya eksik parametre girişi yapıldı.",
            "details": error_details
        }
    )


# -------------------------------------------------------------
# Frontend Arayüz Endpoint'i
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, summary="Yönetim Paneli ve Sepet Simülatörü")
async def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# -------------------------------------------------------------
# 1. Sepet Kampanya Değerlendirme Endpoint'i
# -------------------------------------------------------------
@app.post(
    "/api/v1/kampanya/degerlendir",
    response_model=SepetDegerlendirResponse,
    summary="Sepet Kampanya Değerlendirme (Hit Policy: First)",
    responses={
        200: {"description": "Sepet başarıyla değerlendirildi veya güvenli fallback uygulandı."},
        400: {"model": ErrorResponse, "description": "Geçersiz istek parametreleri."}
    }
)
def evaluate_campaign(context: SepetDegerlendirRequest, db: Session = Depends(get_db)):
    """
    Sepet bağlamını aktif kurallara göre öncelik sırasıyla tarar.
    İlk eşleşen kuralın indirim ve ek faydalarını hesaplar.
    Sunucu/DB arızasında 'fallback_applied: true' ile sepeti korur.
    """
    return evaluate_cart_safe(db, context)


# -------------------------------------------------------------
# 2. Kurallar Yönetimi (Rules CRUD & Management)
# -------------------------------------------------------------
@app.get("/api/v1/kurallar", response_model=List[KuralResponse], summary="Tüm Kuralları Öncelik Sırasıyla Listele")
def list_rules(db: Session = Depends(get_db)):
    return db.query(Kural).order_by(asc(Kural.oncelik_sirasi)).all()


@app.post("/api/v1/kurallar", response_model=KuralResponse, status_code=status.HTTP_201_CREATED, summary="Yeni Kampanya Kuralı Oluştur")
def create_rule(payload: KuralCreate, db: Session = Depends(get_db)):
    # 1. Hediye Ürün veya Kupon Aksiyonu için stok ve geçerlilik doğrulaması
    if payload.aksiyon.aksiyon_tipi == AksiyonTipi.HEDIYE_URUN_EKLE:
        gift = db.query(HediyeUrun).filter(HediyeUrun.id == payload.aksiyon.hediye_urun_id).first()
        if not gift or gift.durum != "AKTIF" or gift.stok_adedi <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seçilen hediye ürün stokta bulunmamaktadır veya geçersizdir."
            )

    elif payload.aksiyon.aksiyon_tipi == AksiyonTipi.KUPON_TANIMLA:
        coupon = db.query(KuponSablon).filter(KuponSablon.id == payload.aksiyon.kupon_sablon_id).first()
        if not coupon or coupon.durum != "AKTIF" or coupon.kullanim_limiti <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seçilen kupon şablonu geçersizdir veya kullanım limiti tükenmiştir."
            )

    # 2. Öncelik Sırası Belirleme & Shift Logic
    next_pri = get_next_priority(db)
    target_pri = payload.oncelik_sirasi if payload.oncelik_sirasi and payload.oncelik_sirasi < next_pri else next_pri

    if payload.oncelik_sirasi and payload.oncelik_sirasi < next_pri:
        reorder_on_create(db, payload.oncelik_sirasi)
        target_pri = payload.oncelik_sirasi

    # 3. Kuralı varsayılan PASIF (veya belirtilen) durumda oluştur
    new_rule = Kural(
        ad=payload.ad,
        kampanya_id=payload.kampanya_id,
        oncelik_sirasi=target_pri,
        durum=payload.durum.value
    )
    db.add(new_rule)
    db.flush()

    # 4. Koşulları Ekle
    for c in payload.kosullar:
        kosul = Kosul(
            kural_id=new_rule.id,
            parametre=c.parametre.value,
            operator=c.operator.value,
            deger=c.deger.strip()
        )
        db.add(kosul)

    # 5. Aksiyonu Ekle
    aksiyon = Aksiyon(
        kural_id=new_rule.id,
        aksiyon_tipi=payload.aksiyon.aksiyon_tipi.value,
        aksiyon_degeri=payload.aksiyon.aksiyon_degeri,
        hediye_urun_id=payload.aksiyon.hediye_urun_id,
        kupon_sablon_id=payload.aksiyon.kupon_sablon_id
    )
    db.add(aksiyon)

    normalize_priorities(db)
    db.commit()
    db.refresh(new_rule)
    return new_rule


@app.get("/api/v1/kurallar/{rule_id}", response_model=KuralResponse, summary="Kural Detayını Getir")
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kural bulunamadı.")
    return rule


@app.put("/api/v1/kurallar/{rule_id}", response_model=KuralResponse, summary="Kuralı Güncelle")
def update_rule(rule_id: int, payload: KuralUpdate, db: Session = Depends(get_db)):
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kural bulunamadı.")

    if payload.ad is not None:
        rule.ad = payload.ad
    if payload.kampanya_id is not None:
        rule.kampanya_id = payload.kampanya_id
    if payload.durum is not None:
        rule.durum = payload.durum.value

    # Öncelik güncellemesi varsa
    if payload.oncelik_sirasi is not None and payload.oncelik_sirasi != rule.oncelik_sirasi:
        reorder_on_update(db, rule.id, payload.oncelik_sirasi)

    # Koşulları güncelle
    if payload.kosullar is not None:
        db.query(Kosul).filter(Kosul.kural_id == rule.id).delete()
        for c in payload.kosullar:
            kosul = Kosul(
                kural_id=rule.id,
                parametre=c.parametre.value,
                operator=c.operator.value,
                deger=c.deger.strip()
            )
            db.add(kosul)

    # Aksiyonu güncelle
    if payload.aksiyon is not None:
        # Stok / kupon doğrulaması
        if payload.aksiyon.aksiyon_tipi == AksiyonTipi.HEDIYE_URUN_EKLE:
            gift = db.query(HediyeUrun).filter(HediyeUrun.id == payload.aksiyon.hediye_urun_id).first()
            if not gift or gift.durum != "AKTIF" or gift.stok_adedi <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Seçilen hediye ürün stokta bulunmamaktadır veya geçersizdir."
                )
        elif payload.aksiyon.aksiyon_tipi == AksiyonTipi.KUPON_TANIMLA:
            coupon = db.query(KuponSablon).filter(KuponSablon.id == payload.aksiyon.kupon_sablon_id).first()
            if not coupon or coupon.durum != "AKTIF" or coupon.kullanim_limiti <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Seçilen kupon şablonu geçersizdir veya kullanım limiti tükenmiştir."
                )

        if rule.aksiyon:
            rule.aksiyon.aksiyon_tipi = payload.aksiyon.aksiyon_tipi.value
            rule.aksiyon.aksiyon_degeri = payload.aksiyon.aksiyon_degeri
            rule.aksiyon.hediye_urun_id = payload.aksiyon.hediye_urun_id
            rule.aksiyon.kupon_sablon_id = payload.aksiyon.kupon_sablon_id
        else:
            aksiyon = Aksiyon(
                kural_id=rule.id,
                aksiyon_tipi=payload.aksiyon.aksiyon_tipi.value,
                aksiyon_degeri=payload.aksiyon.aksiyon_degeri,
                hediye_urun_id=payload.aksiyon.hediye_urun_id,
                kupon_sablon_id=payload.aksiyon.kupon_sablon_id
            )
            db.add(aksiyon)

    normalize_priorities(db)
    db.commit()
    db.refresh(rule)
    return rule


@app.patch("/api/v1/kurallar/{rule_id}/durum", response_model=KuralResponse, summary="Kural Durumunu Değiştir (Aktif/Pasif)")
def toggle_rule_status(rule_id: int, payload: KuralStatusUpdate, db: Session = Depends(get_db)):
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kural bulunamadı.")

    rule.durum = payload.durum.value
    db.commit()
    db.refresh(rule)
    return rule


@app.patch("/api/v1/kurallar/{rule_id}/oncelik", response_model=KuralResponse, summary="Kural Öncelik Sırasını Değiştir (Shift Logic)")
def update_rule_priority(rule_id: int, payload: KuralPriorityUpdate, db: Session = Depends(get_db)):
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kural bulunamadı.")

    reorder_on_update(db, rule_id, payload.yeni_oncelik)
    db.commit()
    db.refresh(rule)
    return rule


@app.delete("/api/v1/kurallar/{rule_id}", summary="Kuralı Sil")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(Kural).filter(Kural.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kural bulunamadı.")

    old_pri = rule.oncelik_sirasi
    db.delete(rule)
    reorder_on_delete(db, old_pri)
    normalize_priorities(db)
    db.commit()
    return {"message": "Kural başarıyla silindi.", "id": rule_id}


# -------------------------------------------------------------
# 3. Referanslar Endpoint'leri (Hediye Ürünler & Kuponlar & Kampanyalar)
# -------------------------------------------------------------
@app.get("/api/v1/referanslar/hediye-urunler", response_model=List[HediyeUrunResponse], summary="Aktif & Stokta Olan Hediye Ürünleri Getir")
def get_active_gift_products(all: bool = False, db: Session = Depends(get_db)):
    query = db.query(HediyeUrun)
    if not all:
        query = query.filter(HediyeUrun.durum == "AKTIF", HediyeUrun.stok_adedi > 0)
    return query.all()


@app.get("/api/v1/referanslar/kuponlar", response_model=List[KuponSablonResponse], summary="Aktif & Geçerli Kupon Şablonlarını Getir")
def get_active_coupons(all: bool = False, db: Session = Depends(get_db)):
    query = db.query(KuponSablon)
    if not all:
        query = query.filter(KuponSablon.durum == "AKTIF", KuponSablon.kullanim_limiti > 0)
    return query.all()


@app.get("/api/v1/kampanyalar", response_model=List[KampanyaResponse], summary="Kampanyaları Listele")
def get_campaigns(db: Session = Depends(get_db)):
    return db.query(Kampanya).order_by(asc(Kampanya.id)).all()


@app.post("/api/v1/kampanyalar", response_model=KampanyaResponse, status_code=status.HTTP_201_CREATED, summary="Yeni Kampanya Oluştur")
def create_campaign(payload: KampanyaCreate, db: Session = Depends(get_db)):
    kampanya = Kampanya(
        ad=payload.ad,
        aciklama=payload.aciklama,
        baslangic_tarihi=payload.baslangic_tarihi,
        bitis_tarihi=payload.bitis_tarihi
    )
    db.add(kampanya)
    db.commit()
    db.refresh(kampanya)
    return kampanya
