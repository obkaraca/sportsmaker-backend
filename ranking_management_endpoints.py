"""
Sıralama Yönetimi (Ranking Management) Endpoint'leri
Sadece admin kullanıcılar erişebilir
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import uuid
import io
import pandas as pd
from auth import get_current_user

ranking_router = APIRouter(prefix="/api/ranking-management", tags=["ranking-management"])

# Database reference
db = None

def set_ranking_db(database):
    global db
    db = database

# ==================== MODELS ====================

class RankingEntry(BaseModel):
    user_id: str
    sport_code: str
    points: float = 0
    national_rank: Optional[int] = None
    city_rank: Optional[int] = None

class BulkRankingUpdate(BaseModel):
    rankings: List[RankingEntry]

# ==================== HELPERS ====================

async def check_admin(current_user: dict):
    """Admin kontrolü"""
    if current_user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gereklidir")

# ==================== ENDPOINTS ====================

@ranking_router.get("/sports")
async def get_available_sports(current_user: dict = Depends(get_current_user)):
    """Mevcut spor dallarını getir"""
    await check_admin(current_user)
    
    # Varsayılan spor dalları
    default_sports = [
        {"code": "TABLE_TENNIS", "name": "Masa Tenisi", "icon": "🏓"},
        {"code": "TENNIS", "name": "Tenis", "icon": "🎾"},
        {"code": "BADMINTON", "name": "Badminton", "icon": "🏸"},
        {"code": "SQUASH", "name": "Squash", "icon": "🎯"},
        {"code": "PADEL", "name": "Padel", "icon": "🎾"}
    ]
    
    # Veritabanından ek sporları al
    if db:
        db_sports = await db.sports.find().to_list(100)
        for sport in db_sports:
            if sport.get("code") not in [s["code"] for s in default_sports]:
                default_sports.append({
                    "code": sport.get("code"),
                    "name": sport.get("name"),
                    "icon": sport.get("icon", "🏅")
                })
    
    return {"sports": default_sports}


@ranking_router.get("/users")
async def get_users_with_rankings(
    sport_code: Optional[str] = None,
    city: Optional[str] = None,
    gender: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcıları sıralama bilgileriyle getir - Sadece PLAYER rolündeki kullanıcılar"""
    await check_admin(current_user)
    
    # Filtre oluştur - Sadece PLAYER rolündeki kullanıcıları al
    query = {"user_type": "player"}
    
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    
    if gender:
        query["gender"] = gender
    
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    # Toplam sayı
    total = await db.users.count_documents(query)
    
    # Kullanıcıları al - isme göre sırala
    skip = (page - 1) * limit
    users = await db.users.find(query).sort("full_name", 1).skip(skip).limit(limit).to_list(limit)
    
    # Ranking bilgilerini ekle
    result = []
    for user in users:
        user_id = user.get("id")
        
        # user_rankings koleksiyonundan sıralamaları al
        rankings = await db.user_rankings.find({"user_id": user_id}).to_list(100)
        rankings_dict = {}
        for r in rankings:
            sport_code = r.get("sport_code")
            if sport_code:
                rankings_dict[sport_code] = {
                    "points": r.get("points", 0),
                    "national_rank": r.get("national_rank"),
                    "city_rank": r.get("city_rank")
                }
        
        result.append({
            "id": user_id,
            "full_name": user.get("full_name", ""),
            "email": user.get("email", ""),
            "gender": user.get("gender", ""),
            "city": user.get("city", ""),
            "phone": user.get("phone", ""),
            "rankings": rankings_dict
        })
    
    return {
        "users": result,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }


@ranking_router.post("/update")
async def update_user_ranking(
    entry: RankingEntry,
    current_user: dict = Depends(get_current_user)
):
    """Tek kullanıcının sıralamasını güncelle"""
    await check_admin(current_user)
    
    ranking_doc = {
        "user_id": entry.user_id,
        "sport_code": entry.sport_code,
        "points": entry.points,
        "national_rank": entry.national_rank,
        "city_rank": entry.city_rank,
        "updated_at": datetime.utcnow(),
        "updated_by": current_user.get("id")
    }
    
    # Upsert
    await db.user_rankings.update_one(
        {"user_id": entry.user_id, "sport_code": entry.sport_code},
        {"$set": ranking_doc},
        upsert=True
    )
    
    return {"status": "success", "message": "Sıralama güncellendi"}


@ranking_router.post("/bulk-update")
async def bulk_update_rankings(
    data: BulkRankingUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Toplu sıralama güncelleme"""
    await check_admin(current_user)
    
    updated = 0
    errors = []
    
    for entry in data.rankings:
        try:
            ranking_doc = {
                "user_id": entry.user_id,
                "sport_code": entry.sport_code,
                "points": entry.points,
                "national_rank": entry.national_rank,
                "city_rank": entry.city_rank,
                "updated_at": datetime.utcnow(),
                "updated_by": current_user.get("id")
            }
            
            await db.user_rankings.update_one(
                {"user_id": entry.user_id, "sport_code": entry.sport_code},
                {"$set": ranking_doc},
                upsert=True
            )
            updated += 1
        except Exception as e:
            errors.append({"user_id": entry.user_id, "error": str(e)})
    
    return {
        "status": "success",
        "updated": updated,
        "errors": errors
    }


@ranking_router.post("/import-excel")
async def import_rankings_from_excel(
    file: UploadFile = File(...),
    sport_code: str = Query(..., description="Spor dalı kodu"),
    current_user: dict = Depends(get_current_user)
):
    """Excel'den sıralama verisi içe aktar"""
    await check_admin(current_user)
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Sadece Excel (.xlsx, .xls) veya CSV dosyaları kabul edilir")
    
    try:
        # Dosyayı oku
        content = await file.read()
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        # Kolon isimlerini normalize et
        df.columns = df.columns.str.lower().str.strip()
        
        # Gerekli kolonları kontrol et
        required_cols = []
        name_col = None
        email_col = None
        
        # İsim kolonu bul
        for col in ['ad soyad', 'isim', 'name', 'full_name', 'kullanıcı adı', 'sporcu adı']:
            if col in df.columns:
                name_col = col
                break
        
        # Email kolonu bul (opsiyonel)
        for col in ['email', 'e-posta', 'eposta', 'mail']:
            if col in df.columns:
                email_col = col
                break
        
        if not name_col:
            raise HTTPException(
                status_code=400, 
                detail="Excel'de 'Ad Soyad' veya 'İsim' kolonu bulunamadı"
            )
        
        # Puan kolonu bul
        points_col = None
        for col in ['puan', 'points', 'rating', 'skor', 'score']:
            if col in df.columns:
                points_col = col
                break
        
        # Ülke sırası kolonu bul
        national_rank_col = None
        for col in ['ülke sırası', 'ulke sirasi', 'national_rank', 'türkiye sırası', 'tr sıra', 'sıra']:
            if col in df.columns:
                national_rank_col = col
                break
        
        # Şehir sırası kolonu bul
        city_rank_col = None
        for col in ['şehir sırası', 'sehir sirasi', 'city_rank', 'il sırası', 'il sıra']:
            if col in df.columns:
                city_rank_col = col
                break
        
        # Verileri işle
        updated = 0
        created = 0
        not_found = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                name = str(row[name_col]).strip() if pd.notna(row[name_col]) else None
                if not name:
                    continue
                
                # Kullanıcıyı bul
                user = None
                
                # Önce email ile ara (varsa)
                if email_col and pd.notna(row.get(email_col)):
                    email = str(row[email_col]).strip().lower()
                    user = await db.users.find_one({"email": email})
                
                # Email ile bulunamadıysa isim ile ara
                if not user:
                    # Tam eşleşme dene
                    user = await db.users.find_one({
                        "full_name": {"$regex": f"^{name}$", "$options": "i"}
                    })
                
                # Hala bulunamadıysa kısmi eşleşme dene
                if not user:
                    user = await db.users.find_one({
                        "full_name": {"$regex": name, "$options": "i"}
                    })
                
                if not user:
                    not_found.append({"row": idx + 2, "name": name})
                    continue
                
                # Ranking verilerini hazırla
                ranking_doc = {
                    "user_id": user.get("id"),
                    "sport_code": sport_code,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_user.get("id")
                }
                
                if points_col and pd.notna(row.get(points_col)):
                    try:
                        ranking_doc["points"] = float(row[points_col])
                    except:
                        pass
                
                if national_rank_col and pd.notna(row.get(national_rank_col)):
                    try:
                        ranking_doc["national_rank"] = int(row[national_rank_col])
                    except:
                        pass
                
                if city_rank_col and pd.notna(row.get(city_rank_col)):
                    try:
                        ranking_doc["city_rank"] = int(row[city_rank_col])
                    except:
                        pass
                
                # Kaydet
                result = await db.user_rankings.update_one(
                    {"user_id": user.get("id"), "sport_code": sport_code},
                    {"$set": ranking_doc},
                    upsert=True
                )
                
                if result.upserted_id:
                    created += 1
                else:
                    updated += 1
                    
            except Exception as e:
                errors.append({"row": idx + 2, "error": str(e)})
        
        return {
            "status": "success",
            "message": f"{updated} güncellendi, {created} yeni oluşturuldu",
            "updated": updated,
            "created": created,
            "not_found": not_found,
            "errors": errors,
            "total_processed": updated + created
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dosya işlenirken hata: {str(e)}")


@ranking_router.get("/export-excel")
async def export_rankings_to_excel(
    sport_code: Optional[str] = None,
    city: Optional[str] = None,
    gender: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Sıralama verilerini Excel olarak dışa aktar"""
    await check_admin(current_user)
    
    # Kullanıcıları al
    query = {"user_type": {"$in": ["athlete", "user"]}}
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if gender:
        query["gender"] = gender
    
    users = await db.users.find(query).to_list(10000)
    
    # Ranking verilerini al
    ranking_query = {}
    if sport_code:
        ranking_query["sport_code"] = sport_code
    
    rankings = await db.user_rankings.find(ranking_query).to_list(50000)
    rankings_map = {}
    for r in rankings:
        key = f"{r.get('user_id')}_{r.get('sport_code')}"
        rankings_map[key] = r
    
    # Spor dallarını al
    sports = [
        {"code": "TABLE_TENNIS", "name": "Masa Tenisi"},
        {"code": "TENNIS", "name": "Tenis"},
        {"code": "BADMINTON", "name": "Badminton"},
        {"code": "SQUASH", "name": "Squash"},
        {"code": "PADEL", "name": "Padel"}
    ]
    
    if sport_code:
        sports = [s for s in sports if s["code"] == sport_code]
    
    # DataFrame oluştur
    data = []
    for user in users:
        row = {
            "Ad Soyad": user.get("full_name", ""),
            "Email": user.get("email", ""),
            "Cinsiyet": "Erkek" if user.get("gender") in ["male", "erkek"] else "Kadın" if user.get("gender") in ["female", "kadın"] else "",
            "Şehir": user.get("city", "")
        }
        
        for sport in sports:
            key = f"{user.get('id')}_{sport['code']}"
            ranking = rankings_map.get(key, {})
            
            row[f"{sport['name']} Puan"] = ranking.get("points", "")
            row[f"{sport['name']} Ülke Sırası"] = ranking.get("national_rank", "")
            row[f"{sport['name']} Şehir Sırası"] = ranking.get("city_rank", "")
        
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Excel oluştur
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sıralamalar')
    
    output.seek(0)
    
    filename = f"siralamalar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@ranking_router.delete("/user/{user_id}/sport/{sport_code}")
async def delete_user_ranking(
    user_id: str,
    sport_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Kullanıcının belirli bir spor dalındaki sıralamasını sil"""
    await check_admin(current_user)
    
    result = await db.user_rankings.delete_one({
        "user_id": user_id,
        "sport_code": sport_code
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sıralama bulunamadı")
    
    return {"status": "success", "message": "Sıralama silindi"}
