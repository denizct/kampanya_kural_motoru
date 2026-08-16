"""
main.py – FastAPI uygulaması, tüm API uçları ve Jinja2 template sunumu.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.engine import kampanya_degerlendir
from app.models import (
    Aksiyon,
    HediyeUrun,
    Kosul,
    Kural,
    KuralDurumu,
    KuponSablonu,
)
from app.schemas import (
    DegerlendirmeResponse,
    DegerlendirilecekSepet,
    DurumGuncelle,
    HediyeUrunRead,
    KuponSablonuRead,
    KuralCreate,
    KuralRead,
    OncelikSiralaRequest,
)

# ── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Kampanya Kural Motoru",
    description="Kampanya ve kural değerlendirme motoru – Admin panel + API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Static files
static_path = BASE_DIR / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["frontend"])
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Değerlendirme ─────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/kampanya/degerlendir",
    response_model=DegerlendirmeResponse,
    tags=["motor"],
    summary="Sepeti kampanya kurallarına göre değerlendir",
)
def degerlendir(sepet: DegerlendirilecekSepet, db: Session = Depends(get_db)):
    return kampanya_degerlendir(sepet, db)


# ── Kural CRUD ────────────────────────────────────────────────────────────────

@app.get(
    "/api/v1/kurallar",
    response_model=list[KuralRead],
    tags=["kurallar"],
    summary="Tüm kuralları öncelik sırasıyla listele",
)
def kurallar_listele(db: Session = Depends(get_db)):
    return (
        db.query(Kural)
        .options(
            joinedload(Kural.kosullar),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.hediye_urun),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.kupon_sablonu),
            joinedload(Kural.kampanya),
        )
        .order_by(Kural.oncelik_sirasi.asc())
        .all()
    )


@app.post(
    "/api/v1/kurallar",
    response_model=KuralRead,
    status_code=status.HTTP_201_CREATED,
    tags=["kurallar"],
    summary="Yeni kural ekle – Shift algoritması ile öncelik kaydırma",
)
def kural_ekle(payload: KuralCreate, db: Session = Depends(get_db)):
    hedef_siralama = payload.oncelik_sirasi
    toplam = db.query(Kural).count()

    # Geçerli aralık: 1 .. N+1
    if hedef_siralama < 1 or hedef_siralama > toplam + 1:
        raise HTTPException(
            status_code=400,
            detail=f"Öncelik sırası 1 ile {toplam + 1} arasında olmalıdır (mevcut kural sayısı: {toplam}).",
        )

    # ── Bulk SQL Shift ────────────────────────────────────────────────────
    # Tek bir SQL UPDATE ile oncelik_sirasi >= K satırlarını atomik olarak +1 artır.
    # ORM döngüsü yerine ham SQL – UNIQUE kısıtlaması ihlali kesinlikle yaşanmaz.
    db.execute(
        text("UPDATE kurallar SET oncelik_sirasi = oncelik_sirasi + 1 WHERE oncelik_sirasi >= :k"),
        {"k": hedef_siralama},
    )
    db.flush()
    # ────────────────────────────────────────────────────────────────────────

    kural = Kural(
        kampanya_id=payload.kampanya_id,
        ad=payload.ad,
        oncelik_sirasi=hedef_siralama,
        durum=payload.durum,
    )
    db.add(kural)
    db.flush()

    for k in payload.kosullar:
        db.add(Kosul(
            kural_id=kural.id,
            parametre=k.parametre,
            operator=k.operator,
            deger=k.deger,
        ))

    a = payload.aksiyon
    db.add(Aksiyon(
        kural_id=kural.id,
        aksiyon_tipi=a.aksiyon_tipi,
        aksiyon_degeri=a.aksiyon_degeri,
        hediye_urun_id=a.hediye_urun_id,
        kupon_sablon_id=a.kupon_sablon_id,
    ))

    db.commit()
    db.refresh(kural)

    return (
        db.query(Kural)
        .options(
            joinedload(Kural.kosullar),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.hediye_urun),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.kupon_sablonu),
            joinedload(Kural.kampanya),
        )
        .filter(Kural.id == kural.id)
        .one()
    )


@app.patch(
    "/api/v1/kurallar/{kural_id}/durum",
    response_model=KuralRead,
    tags=["kurallar"],
    summary="Kural durumunu Aktif/Pasif yap",
)
def durum_guncelle(kural_id: int, payload: DurumGuncelle, db: Session = Depends(get_db)):
    kural = db.query(Kural).filter(Kural.id == kural_id).first()
    if not kural:
        raise HTTPException(status_code=404, detail="Kural bulunamadı.")
    kural.durum = payload.durum
    db.commit()
    db.refresh(kural)
    return (
        db.query(Kural)
        .options(
            joinedload(Kural.kosullar),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.hediye_urun),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.kupon_sablonu),
            joinedload(Kural.kampanya),
        )
        .filter(Kural.id == kural.id)
        .one()
    )


@app.put(
    "/api/v1/kurallar/oncelik-sirala",
    response_model=list[KuralRead],
    tags=["kurallar"],
    summary="Kuralların öncelik sıralarını toplu güncelle",
)
def oncelik_sirala(payload: OncelikSiralaRequest, db: Session = Depends(get_db)):
    # Geçici olarak unique kısıtlamayı aşmak için negatif değer ata
    ids = [item.id for item in payload.kurallar]
    kurallar_map = {k.id: k for k in db.query(Kural).filter(Kural.id.in_(ids)).all()}

    if len(kurallar_map) != len(ids):
        raise HTTPException(status_code=404, detail="Bazı kural ID'leri bulunamadı.")

    # Önce negatif geçici değerler ata
    for item in payload.kurallar:
        kurallar_map[item.id].oncelik_sirasi = -item.id
    db.flush()

    # Sonra gerçek değerleri ata
    for item in payload.kurallar:
        kurallar_map[item.id].oncelik_sirasi = item.oncelik_sirasi
    db.commit()

    return (
        db.query(Kural)
        .options(
            joinedload(Kural.kosullar),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.hediye_urun),
            joinedload(Kural.aksiyon).joinedload(Aksiyon.kupon_sablonu),
            joinedload(Kural.kampanya),
        )
        .order_by(Kural.oncelik_sirasi.asc())
        .all()
    )


@app.delete(
    "/api/v1/kurallar/{kural_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["kurallar"],
    summary="Kural sil – Compact algoritması ile sıra boşluğu kapatılır",
)
def kural_sil(kural_id: int, db: Session = Depends(get_db)):
    kural = db.query(Kural).filter(Kural.id == kural_id).first()
    if not kural:
        raise HTTPException(status_code=404, detail="Kural bulunamadı.")

    silinen_sira = kural.oncelik_sirasi
    db.delete(kural)
    db.flush()

    # ── Bulk SQL Compact ──────────────────────────────────────────────────
    # Tek bir SQL UPDATE ile silinen sıradan büyük tüm satırları -1 azalt.
    # Atomik işlem – UNIQUE kısıtlaması ihlali yaşanmaz.
    db.execute(
        text("UPDATE kurallar SET oncelik_sirasi = oncelik_sirasi - 1 WHERE oncelik_sirasi > :s"),
        {"s": silinen_sira},
    )
    # ────────────────────────────────────────────────────────────────────────

    db.commit()


# ── Referans Verileri ─────────────────────────────────────────────────────────

@app.get(
    "/api/v1/referans/hediye-urunler",
    response_model=list[HediyeUrunRead],
    tags=["referans"],
    summary="Aktif hediye ürünleri listele",
)
def hediye_urunler(db: Session = Depends(get_db)):
    return db.query(HediyeUrun).filter(HediyeUrun.durum == "AKTIF").all()


@app.get(
    "/api/v1/referans/kupon-sablonlari",
    response_model=list[KuponSablonuRead],
    tags=["referans"],
    summary="Aktif kupon şablonlarını listele",
)
def kupon_sablonlari(db: Session = Depends(get_db)):
    return db.query(KuponSablonu).filter(KuponSablonu.durum == "AKTIF").all()
