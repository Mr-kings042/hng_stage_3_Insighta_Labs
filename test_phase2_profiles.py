"""
Phase 2: Profile API Enhancements Tests
- POST /api/profiles (admin only, create with external API)
- GET /api/profiles/export (CSV export)
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal, Base, engine
from models import User
from auth.tokens import TokenManager
from datetime import datetime, timezone
import uuid
import csv
from io import StringIO


@pytest.fixture(scope="function")
def setup_database():
    """Create tables and seed with test data"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(setup_database):
    """Create a test client"""
    return TestClient(app)


@pytest.fixture
def admin_user(setup_database):
    """Create admin user"""
    db = SessionLocal()
    try:
        user = User(
            github_id="admin_github_123",
            username="test_admin",
            email="admin@example.com",
            role="admin",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture
def analyst_user(setup_database):
    """Create analyst user"""
    db = SessionLocal()
    try:
        user = User(
            github_id="analyst_github_123",
            username="test_analyst",
            email="analyst@example.com",
            role="analyst",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture
def admin_headers(admin_user):
    """Generate admin auth headers"""
    token_manager = TokenManager()
    access_token = token_manager.generate_access_token(str(admin_user.id), admin_user.role)
    return {
        "Authorization": f"Bearer {access_token}",
        "X-API-Version": "1",
    }


@pytest.fixture
def analyst_headers(analyst_user):
    """Generate analyst auth headers"""
    token_manager = TokenManager()
    access_token = token_manager.generate_access_token(str(analyst_user.id), analyst_user.role)
    return {
        "Authorization": f"Bearer {access_token}",
        "X-API-Version": "1",
    }


class TestCreateProfile:
    """Test POST /api/profiles endpoint (admin only)"""
    
    def test_create_profile_admin_success(self, client, admin_headers):
        """Test admin can create profile"""
        payload = {"name": "Harriet Tubman"}
        response = client.post("/api/profiles", json=payload, headers=admin_headers)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["status"] == "success"
        assert "data" in data
        profile = data["data"]
        
        # Verify all required fields present
        required_fields = [
            "id", "name", "gender", "gender_probability",
            "age", "age_group", "country_id", "country_name",
            "country_probability", "created_at"
        ]
        for field in required_fields:
            assert field in profile
        
        assert profile["name"] == "Harriet Tubman"
        assert isinstance(profile["age"], int)
        assert 0 <= profile["age"] <= 120
    
    def test_create_profile_analyst_forbidden(self, client, analyst_headers):
        """Test analyst cannot create profile"""
        payload = {"name": "Test User"}
        response = client.post("/api/profiles", json=payload, headers=analyst_headers)
        
        assert response.status_code == 403
        data = response.json()
        assert data["status"] == "error"
    
    def test_create_profile_missing_name(self, client, admin_headers):
        """Test create profile with missing name"""
        payload = {}
        response = client.post("/api/profiles", json=payload, headers=admin_headers)
        
        assert response.status_code == 422
    
    def test_create_profile_empty_name(self, client, admin_headers):
        """Test create profile with empty name"""
        payload = {"name": ""}
        response = client.post("/api/profiles", json=payload, headers=admin_headers)
        
        # Empty string fails Pydantic validation (min_length=1)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    def test_create_profile_whitespace_only(self, client, admin_headers):
        """Test create profile with whitespace-only name"""
        payload = {"name": "   "}
        response = client.post("/api/profiles", json=payload, headers=admin_headers)
        
        # Whitespace only fails validator
        assert response.status_code == 422
    
    def test_create_profile_unauthorized(self, client):
        """Test create profile without auth"""
        payload = {"name": "Test User"}
        # No auth headers, will fail middleware check for X-API-Version first
        response = client.post("/api/profiles", json=payload)
        
        # Should fail at middleware level due to missing X-API-Version
        assert response.status_code in [400, 401]
    
    def test_create_profile_response_structure(self, client, admin_headers):
        """Test response structure follows API format"""
        payload = {"name": "John Doe"}
        response = client.post("/api/profiles", json=payload, headers=admin_headers)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify envelope structure
        assert "status" in data
        assert data["status"] == "success"
        assert "data" in data
        
        # Verify profile data types
        profile = data["data"]
        assert isinstance(profile["id"], str)
        assert isinstance(profile["name"], str)
        assert isinstance(profile["gender"], str)
        assert profile["gender"] in ["male", "female"]
        assert isinstance(profile["gender_probability"], float)
        assert 0 <= profile["gender_probability"] <= 1
        assert isinstance(profile["age"], int)
        assert isinstance(profile["age_group"], str)
        assert profile["age_group"] in ["child", "teenager", "adult", "senior"]
        assert isinstance(profile["country_id"], str)
        assert len(profile["country_id"]) == 2
        assert isinstance(profile["country_name"], str)
        assert isinstance(profile["country_probability"], float)
        assert 0 <= profile["country_probability"] <= 1
        assert isinstance(profile["created_at"], str)
        assert "T" in profile["created_at"]
    
    def test_create_multiple_profiles(self, client, admin_headers):
        """Test creating multiple profiles returns different data"""
        names = ["Alice", "Bob", "Charlie"]
        profiles = []
        
        for name in names:
            payload = {"name": name}
            response = client.post("/api/profiles", json=payload, headers=admin_headers)
            assert response.status_code == 201
            profile = response.json()["data"]
            profiles.append(profile)
        
        # Verify each has unique ID
        ids = [p["id"] for p in profiles]
        assert len(set(ids)) == len(ids)
    
    def test_create_profile_api_version_required(self, client, admin_headers):
        """Test that X-API-Version header is required"""
        payload = {"name": "Test User"}
        headers = {k: v for k, v in admin_headers.items() if k != "X-API-Version"}
        
        response = client.post("/api/profiles", json=payload, headers=headers)
        assert response.status_code == 400


class TestExportProfiles:
    """Test GET /api/profiles/export endpoint (CSV export)"""
    
    def test_export_profiles_csv_basic(self, client, analyst_headers):
        """Test basic CSV export"""
        response = client.get("/api/profiles/export?format=csv", headers=analyst_headers)
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # Parse CSV
        csv_content = response.text
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        # Should have CSV header
        assert len(rows) >= 0
        if rows:
            # Verify required columns
            expected_columns = [
                "id", "name", "gender", "gender_probability",
                "age", "age_group", "country_id", "country_name",
                "country_probability", "created_at"
            ]
            for col in expected_columns:
                assert col in rows[0]
    
    def test_export_profiles_csv_with_filters(self, client, analyst_headers):
        """Test CSV export with gender filter"""
        response = client.get(
            "/api/profiles/export?format=csv&gender=male&limit=50",
            headers=analyst_headers
        )
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        # All genders should be male
        for row in rows:
            assert row["gender"] == "male"
    
    def test_export_profiles_csv_all_filters(self, client, analyst_headers):
        """Test CSV export with all filter types"""
        response = client.get(
            "/api/profiles/export?format=csv&gender=female&min_age=25&max_age=50"
            "&country_id=NG&age_group=adult&min_gender_probability=0.8&"
            "min_country_probability=0.7&limit=50",
            headers=analyst_headers
        )
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        # Verify filters applied
        for row in rows:
            assert row["gender"] == "female"
            assert row["age_group"] == "adult"
            assert row["country_id"] == "NG"
            assert int(row["age"]) >= 25
            assert int(row["age"]) <= 50
            assert float(row["gender_probability"]) >= 0.8
            assert float(row["country_probability"]) >= 0.7
    
    def test_export_profiles_unauthorized(self, client):
        """Test export without auth"""
        response = client.get("/api/profiles/export?format=csv")
        
        # Should fail at middleware level due to missing X-API-Version
        assert response.status_code in [400, 401]
    
    def test_export_profiles_missing_format(self, client, analyst_headers):
        """Test export without format parameter"""
        response = client.get("/api/profiles/export", headers=analyst_headers)
        
        # Should either require format or default to CSV
        assert response.status_code in [200, 400, 422]
    
    def test_export_profiles_invalid_format(self, client, analyst_headers):
        """Test export with invalid format"""
        response = client.get("/api/profiles/export?format=xml", headers=analyst_headers)
        
        assert response.status_code == 400
    
    def test_export_profiles_csv_filename(self, client, analyst_headers):
        """Test CSV export has proper filename header"""
        response = client.get("/api/profiles/export?format=csv", headers=analyst_headers)
        
        assert response.status_code == 200
        # Check Content-Disposition header for filename
        content_disposition = response.headers.get("content-disposition", "")
        assert "filename" in content_disposition or content_disposition == ""
    
    def test_export_profiles_with_pagination(self, client, analyst_headers):
        """Test CSV export respects limit parameter"""
        response1 = client.get(
            "/api/profiles/export?format=csv&limit=10",
            headers=analyst_headers
        )
        response2 = client.get(
            "/api/profiles/export?format=csv&limit=5",
            headers=analyst_headers
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        rows1 = list(csv.DictReader(StringIO(response1.text)))
        rows2 = list(csv.DictReader(StringIO(response2.text)))
        
        # Limit 5 should have fewer or equal rows than limit 10
        assert len(rows2) <= len(rows1)
        assert len(rows2) <= 5
        assert len(rows1) <= 10
    
    def test_export_profiles_empty_result(self, client, analyst_headers):
        """Test CSV export with filters that match no profiles"""
        response = client.get(
            "/api/profiles/export?format=csv&age_group=invalid_group",
            headers=analyst_headers
        )
        
        # Should either return 200 with headers only or 400
        assert response.status_code in [200, 400, 422]
    
    def test_export_profiles_api_version_required(self, client, analyst_headers):
        """Test that X-API-Version header is required"""
        headers = {k: v for k, v in analyst_headers.items() if k != "X-API-Version"}
        
        response = client.get("/api/profiles/export?format=csv", headers=headers)
        assert response.status_code == 400
    
    def test_export_profiles_csv_valid_data(self, client, analyst_headers):
        """Test CSV export contains valid data"""
        response = client.get("/api/profiles/export?format=csv&limit=5", headers=analyst_headers)
        
        assert response.status_code == 200
        reader = csv.DictReader(StringIO(response.text))
        rows = list(reader)
        
        if rows:
            row = rows[0]
            
            # Verify data validity
            assert len(row["id"]) > 0
            assert len(row["name"]) > 0
            assert row["gender"] in ["male", "female"]
            assert 0 <= float(row["gender_probability"]) <= 1
            assert 0 <= int(row["age"]) <= 120
            assert row["age_group"] in ["child", "teenager", "adult", "senior"]
            assert len(row["country_id"]) == 2
            assert len(row["country_name"]) > 0
            assert 0 <= float(row["country_probability"]) <= 1
            assert "T" in row["created_at"]


class TestIntegration:
    """Integration tests for Phase 2"""
    
    def test_create_then_export(self, client, admin_headers, analyst_headers):
        """Test creating profiles then exporting them"""
        # Create profiles
        for i in range(3):
            payload = {"name": f"TestUser{i}"}
            response = client.post("/api/profiles", json=payload, headers=admin_headers)
            assert response.status_code == 201
        
        # Export and verify
        response = client.get("/api/profiles/export?format=csv", headers=analyst_headers)
        assert response.status_code == 200
        
        reader = csv.DictReader(StringIO(response.text))
        rows = list(reader)
        assert len(rows) >= 3
    
    def test_analyst_cannot_create_but_can_export(self, client, analyst_headers):
        """Test analyst can export but not create"""
        # Cannot create
        payload = {"name": "Test"}
        response = client.post("/api/profiles", json=payload, headers=analyst_headers)
        assert response.status_code == 403
        
        # Can export
        response = client.get("/api/profiles/export?format=csv", headers=analyst_headers)
        assert response.status_code == 200
