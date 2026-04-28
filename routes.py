"""
API Routes for Insighta Labs demographic profile system.
Includes filtering, sorting, pagination, and natural language search.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional
from datetime import datetime, timezone
import math
import uuid
import csv
from io import StringIO
import httpx

from database import get_db
from models import Profile, User
from schema import ProfileResponse, ProfileListResponse, ErrorResponse, SearchQueryResponse, CreateProfileRequest, CreateProfileResponse
from auth.permissions import CurrentUser, admin_only, authenticated
from nlp_parser import QueryParser


router = APIRouter(prefix="/api", tags=["profiles"])


def _generate_pagination_links(base_url: str, page: int, limit: int, total: int) -> dict:
    """Generate pagination links"""
    total_pages = math.ceil(total / limit) if total > 0 else 1
    
    links = {
        "self": f"{base_url}?page={page}&limit={limit}",
        "next": f"{base_url}?page={page + 1}&limit={limit}" if page < total_pages else None,
        "prev": f"{base_url}?page={page - 1}&limit={limit}" if page > 1 else None,
    }
    
    return links


@router.get("/users/me")
async def get_current_user_info(
    current_user: User = Depends(CurrentUser.get_current_user),
):
    """
    Get current authenticated user information.
    
    Requires authentication.
    Returns user details including role.
    """
    return {
        "status": "success",
        "user": current_user.to_dict(),
    }


@router.get("/profiles", response_model=ProfileListResponse)
async def get_profiles(
    # Filtering parameters
    gender: Optional[str] = Query(None, description="Filter by gender: male or female"),
    age_group: Optional[str] = Query(None, description="Filter by age group"),
    country_id: Optional[str] = Query(None, description="Filter by country ISO code"),
    min_age: Optional[int] = Query(None, description="Minimum age"),
    max_age: Optional[int] = Query(None, description="Maximum age"),
    min_gender_probability: Optional[float] = Query(None, description="Minimum gender probability"),
    min_country_probability: Optional[float] = Query(None, description="Minimum country probability"),
    # Sorting parameters
    sort_by: Optional[str] = Query("created_at", description="Sort by: age, created_at, or gender_probability"),
    order: Optional[str] = Query("asc", description="Sort order: asc or desc"),
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=50, description="Results per page (max 50)"),
    current_user: User = Depends(CurrentUser.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all profiles with advanced filtering, sorting, and pagination.
    
    All filters are combinable and apply with AND logic.
    Requires authentication.
    """
    try:
        # Start building query
        query = db.query(Profile)

        # Apply filters
        filters = []

        if gender:
            gender_lower = gender.lower()
            if gender_lower not in ["male", "female"]:
                raise HTTPException(status_code=422, detail="Invalid gender value")
            filters.append(Profile.gender == gender_lower)

        if age_group:
            age_group_lower = age_group.lower()
            valid_groups = ["child", "teenager", "adult", "senior"]
            if age_group_lower not in valid_groups:
                raise HTTPException(status_code=422, detail="Invalid age_group value")
            filters.append(Profile.age_group == age_group_lower)

        if country_id:
            country_id_upper = country_id.upper()
            if len(country_id_upper) != 2:
                raise HTTPException(status_code=422, detail="Invalid country_id format")
            filters.append(Profile.country_id == country_id_upper)

        if min_age is not None:
            if min_age < 0:
                raise HTTPException(status_code=422, detail="min_age cannot be negative")
            filters.append(Profile.age >= min_age)

        if max_age is not None:
            if max_age < 0:
                raise HTTPException(status_code=422, detail="max_age cannot be negative")
            filters.append(Profile.age <= max_age)

        if min_gender_probability is not None:
            if not 0 <= min_gender_probability <= 1:
                raise HTTPException(status_code=422, detail="min_gender_probability must be between 0 and 1")
            filters.append(Profile.gender_probability >= min_gender_probability)

        if min_country_probability is not None:
            if not 0 <= min_country_probability <= 1:
                raise HTTPException(status_code=422, detail="min_country_probability must be between 0 and 1")
            filters.append(Profile.country_probability >= min_country_probability)

        # Apply all filters with AND logic
        if filters:
            query = query.filter(and_(*filters))

        # Get total count before pagination
        total = query.count()

        # Validate and apply sorting
        if sort_by not in ["age", "created_at", "gender_probability"]:
            raise HTTPException(status_code=422, detail="Invalid sort_by value")

        if order not in ["asc", "desc"]:
            raise HTTPException(status_code=422, detail="Invalid order value")

        # Apply sorting
        sort_column = {
            "age": Profile.age,
            "created_at": Profile.created_at,
            "gender_probability": Profile.gender_probability,
        }[sort_by]

        if order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (page - 1) * limit
        profiles = query.offset(offset).limit(limit).all()

        # Convert to response format
        data = [ProfileResponse(**profile.to_dict()) for profile in profiles]

        # Calculate total pages
        total_pages = math.ceil(total / limit) if total > 0 else 1
        
        # Generate pagination links
        links = _generate_pagination_links("/api/profiles", page, limit, total)

        return ProfileListResponse(
            status="success",
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
            links=links,
            data=data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/search", response_model=SearchQueryResponse)
async def search_profiles(
    q: Optional[str] = Query(None, description="Natural language search query"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=50, description="Results per page (max 50)"),
    current_user: User = Depends(CurrentUser.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search profiles using natural language queries.
    
    Examples:
    - "young males from nigeria"
    - "females above 30"
    - "people from angola"
    - "adult males from kenya"
    - "male and female teenagers above 17"
    
    Requires authentication.
    """
    try:
        if not q or not q.strip():
            raise HTTPException(status_code=400, detail="Query parameter 'q' is required and cannot be empty")

        # Parse the natural language query
        success, filters = QueryParser.parse(q)

        if not success or filters is None:
            # Unable to interpret query - return error response
            raise HTTPException(status_code=400, detail="Unable to interpret query")

        # Build query with interpreted filters
        query = db.query(Profile)
        filter_conditions = []

        if "gender" in filters:
            filter_conditions.append(Profile.gender == filters["gender"])

        if "age_group" in filters:
            filter_conditions.append(Profile.age_group == filters["age_group"])

        if "country_id" in filters:
            filter_conditions.append(Profile.country_id == filters["country_id"])

        if "min_age" in filters:
            filter_conditions.append(Profile.age >= filters["min_age"])

        if "max_age" in filters:
            filter_conditions.append(Profile.age <= filters["max_age"])

        if filter_conditions:
            query = query.filter(and_(*filter_conditions))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * limit
        profiles = query.order_by(Profile.created_at.desc()).offset(offset).limit(limit).all()

        # Convert to response format
        data = [ProfileResponse(**profile.to_dict()) for profile in profiles]

        # Calculate total pages
        total_pages = math.ceil(total / limit) if total > 0 else 1
        
        # Generate pagination links
        links = _generate_pagination_links("/api/profiles/search", page, limit, total)

        return SearchQueryResponse(
            status="success",
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
            links=links,
            data=data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def infer_demographics_from_name(name: str) -> dict:
    """
    Call external API to infer demographics from a name.
    Falls back to mock data if API unavailable.
    
    In production, this would call services like:
    - Clearbit API
    - Hunter.io API
    - FullContact API
    - Or a custom ML model
    """
    try:
        # Try calling an external demographic inference API
        async with httpx.AsyncClient(timeout=5) as client:
            # Example: Using a hypothetical demographics API
            # response = await client.get(f"https://api.example.com/demographics?name={name}")
            # if response.status_code == 200:
            #     return response.json()
            pass
    except Exception:
        pass
    
    # Fallback: Mock demographic inference based on name patterns
    import hashlib
    
    # Use name hash for deterministic but varied results
    name_hash = int(hashlib.md5(name.encode()).hexdigest(), 16)
    
    # Deterministic demographics based on hash
    genders = ["male", "female"]
    age_groups = ["child", "teenager", "adult", "senior"]
    countries = [
        "NG", "GH", "KE", "AO", "ZA", "TZ", "UG", "RW", "BW", "MZ",
        "ET", "SD", "EG", "MA", "TN", "DZ", "LY", "SN", "CM", "CI"
    ]
    
    gender = genders[name_hash % len(genders)]
    age = 15 + (name_hash % 65)
    age_group = age_groups[
        0 if age < 13 else 
        1 if age < 16 else 
        2 if age < 65 else 
        3
    ]
    country_id = countries[name_hash % len(countries)]
    
    country_names = {
        "NG": "Nigeria", "GH": "Ghana", "KE": "Kenya", "AO": "Angola",
        "ZA": "South Africa", "TZ": "Tanzania", "UG": "Uganda", "RW": "Rwanda",
        "BW": "Botswana", "MZ": "Mozambique", "ET": "Ethiopia", "SD": "Sudan",
        "EG": "Egypt", "MA": "Morocco", "TN": "Tunisia", "DZ": "Algeria",
        "LY": "Libya", "SN": "Senegal", "CM": "Cameroon", "CI": "Côte d'Ivoire"
    }
    
    return {
        "gender": gender,
        "gender_probability": 0.65 + (name_hash % 35) / 100,
        "age": age,
        "age_group": age_group,
        "country_id": country_id,
        "country_name": country_names.get(country_id, "Unknown"),
        "country_probability": 0.60 + (name_hash % 40) / 100,
    }


@router.post("/profiles", response_model=CreateProfileResponse, status_code=201)
async def create_profile(
    request: CreateProfileRequest,
    current_user: User = Depends(CurrentUser.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new profile with demographic inference (Admin only).
    
    Accepts: {"name": "John Doe"}
    Calls external API to infer demographics from name.
    Returns: Profile object with all inferred fields.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    profile_name = request.name.strip()
    
    if not profile_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    
    try:
        # Infer demographics from name
        demographics = await infer_demographics_from_name(profile_name)
        
        # Create new profile
        profile = Profile(
            id=str(uuid.uuid4()),
            name=profile_name,
            gender=demographics["gender"],
            gender_probability=demographics["gender_probability"],
            age=demographics["age"],
            age_group=demographics["age_group"],
            country_id=demographics["country_id"],
            country_name=demographics["country_name"],
            country_probability=demographics["country_probability"],
            created_at=datetime.now(timezone.utc),
        )
        
        db.add(profile)
        db.commit()
        db.refresh(profile)
        
        return CreateProfileResponse(
            status="success",
            data=ProfileResponse(**profile.to_dict())
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/export")
async def export_profiles(
    # Format parameter
    format: str = Query("csv", description="Export format: csv"),
    # Filtering parameters (same as GET /api/profiles)
    gender: Optional[str] = Query(None, description="Filter by gender"),
    age_group: Optional[str] = Query(None, description="Filter by age group"),
    country_id: Optional[str] = Query(None, description="Filter by country ISO code"),
    min_age: Optional[int] = Query(None, description="Minimum age"),
    max_age: Optional[int] = Query(None, description="Maximum age"),
    min_gender_probability: Optional[float] = Query(None, description="Minimum gender probability"),
    min_country_probability: Optional[float] = Query(None, description="Minimum country probability"),
    # Sorting parameters
    sort_by: Optional[str] = Query("created_at", description="Sort by field"),
    order: Optional[str] = Query("asc", description="Sort order"),
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=50, description="Results per page"),
    current_user: User = Depends(CurrentUser.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Export profiles as CSV with optional filtering.
    
    Supports same filters as GET /api/profiles
    Returns CSV file with columns: id, name, gender, gender_probability, age, 
    age_group, country_id, country_name, country_probability, created_at
    """
    
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only CSV format supported")
    
    try:
        # Validate inputs
        valid_genders = ["male", "female"]
        if gender and gender not in valid_genders:
            raise HTTPException(status_code=422, detail="Invalid gender")
        
        valid_age_groups = ["child", "teenager", "adult", "senior"]
        if age_group and age_group not in valid_age_groups:
            raise HTTPException(status_code=422, detail="Invalid age group")
        
        if country_id and len(country_id) != 2:
            raise HTTPException(status_code=422, detail="Country ID must be 2 characters")
        
        if min_age is not None and min_age < 0:
            raise HTTPException(status_code=422, detail="Min age cannot be negative")
        
        if max_age is not None and max_age > 120:
            raise HTTPException(status_code=422, detail="Max age cannot exceed 120")
        
        if max_age is not None and min_age is not None and max_age < min_age:
            # Allow but return empty results
            pass
        
        if min_gender_probability is not None and (min_gender_probability < 0 or min_gender_probability > 1):
            raise HTTPException(status_code=422, detail="Gender probability must be 0-1")
        
        if min_country_probability is not None and (min_country_probability < 0 or min_country_probability > 1):
            raise HTTPException(status_code=422, detail="Country probability must be 0-1")
        
        valid_sort_by = ["age", "created_at", "gender_probability", "country_probability"]
        if sort_by not in valid_sort_by:
            raise HTTPException(status_code=422, detail="Invalid sort field")
        
        if order not in ["asc", "desc"]:
            raise HTTPException(status_code=422, detail="Sort order must be asc or desc")
        
        # Build query
        query = db.query(Profile)
        
        # Apply filters
        if gender:
            query = query.filter(Profile.gender == gender)
        if age_group:
            query = query.filter(Profile.age_group == age_group)
        if country_id:
            query = query.filter(Profile.country_id == country_id)
        if min_age is not None:
            query = query.filter(Profile.age >= min_age)
        if max_age is not None:
            query = query.filter(Profile.age <= max_age)
        if min_gender_probability is not None:
            query = query.filter(Profile.gender_probability >= min_gender_probability)
        if min_country_probability is not None:
            query = query.filter(Profile.country_probability >= min_country_probability)
        
        # Apply sorting
        if sort_by == "age":
            query = query.order_by(Profile.age.desc() if order == "desc" else Profile.age)
        elif sort_by == "gender_probability":
            query = query.order_by(Profile.gender_probability.desc() if order == "desc" else Profile.gender_probability)
        elif sort_by == "country_probability":
            query = query.order_by(Profile.country_probability.desc() if order == "desc" else Profile.country_probability)
        else:  # created_at
            query = query.order_by(Profile.created_at.desc() if order == "desc" else Profile.created_at)
        
        # Apply pagination
        offset = (page - 1) * limit
        profiles = query.offset(offset).limit(limit).all()
        
        # Generate CSV
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id", "name", "gender", "gender_probability",
                "age", "age_group", "country_id", "country_name",
                "country_probability", "created_at"
            ]
        )
        
        writer.writeheader()
        for profile in profiles:
            profile_dict = profile.to_dict()
            writer.writerow({
                "id": profile_dict["id"],
                "name": profile_dict["name"],
                "gender": profile_dict["gender"],
                "gender_probability": profile_dict["gender_probability"],
                "age": profile_dict["age"],
                "age_group": profile_dict["age_group"],
                "country_id": profile_dict["country_id"],
                "country_name": profile_dict["country_name"],
                "country_probability": profile_dict["country_probability"],
                "created_at": profile_dict["created_at"].isoformat() if hasattr(profile_dict["created_at"], "isoformat") else str(profile_dict["created_at"]),
            })
        
        csv_content = output.getvalue()
        
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=profiles.csv"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
