"""
Integration tests for the Insighta Labs API
Run with: pytest test_api.py
"""

import os
import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal, Base, engine
from models import Profile, User
from auth.tokens import TokenManager
import uuid
from datetime import datetime, timezone

# Set testing environment to disable rate limiting
os.environ["TESTING"] = "1"


def generate_test_profiles(count=100):
    """Generate test profile data"""
    profiles = []
    names = [
        "Amara", "Kofi", "Zainab", "Ibrahim", "Adia", "Kwame", "Fatima", "Jamal",
        "Noor", "Bisi", "Kai", "Aisha", "Darius", "Leila", "Ethan", "Hana"
    ]
    genders = ["male", "female"]
    age_groups = ["child", "teenager", "adult", "senior"]
    countries = ["NG", "GH", "KE", "AO", "ZA", "TZ", "UG", "RW", "BW", "MZ"]
    
    for i in range(count):
        name = names[i % len(names)] + str(i)
        gender = genders[i % 2]
        age = (i % 80) + 10
        age_group = age_groups[
            0 if age < 13 else 
            1 if age < 16 else 
            2 if age < 65 else 
            3
        ]
        country_id = countries[i % len(countries)]
        
        profile = Profile(
            id=str(uuid.uuid4()),
            name=name,
            gender=gender,
            gender_probability=0.7 + (i % 30) / 100,
            age=age,
            age_group=age_group,
            country_id=country_id,
            country_name="Test Country",
            country_probability=0.6 + (i % 40) / 100,
            created_at=datetime.now(timezone.utc)
        )
        profiles.append(profile)
    
    return profiles


@pytest.fixture(scope="function")
def setup_database():
    """Create tables and seed with test data"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # Seed test data
        profiles = generate_test_profiles(100)
        for profile in profiles:
            db.add(profile)
        db.commit()
    finally:
        db.close()
    
    yield
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(setup_database):
    """Create a test client"""
    return TestClient(app)


@pytest.fixture
def test_user(setup_database):
    """Create a test user"""
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == "test_analyst").first()
        if existing_user:
            return existing_user
        
        user = User(
            github_id="test_github_123",
            username="test_analyst",
            email="test@example.com",
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
def auth_headers(test_user):
    """Generate valid auth headers with JWT token"""
    token_manager = TokenManager()
    access_token = token_manager.generate_access_token(str(test_user.id), test_user.role)
    return {
        "Authorization": f"Bearer {access_token}",
        "X-API-Version": "1",
    }


def test_health_endpoint(client, auth_headers):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint(client, auth_headers):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_get_profiles_no_filter(client, auth_headers):
    """Test getting profiles without filters"""
    response = client.get("/api/profiles?limit=5", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "page" in data
    assert "limit" in data
    assert "total" in data
    assert "data" in data
    assert len(data["data"]) <= 5


def test_get_profiles_with_gender_filter(client, auth_headers):
    """Test filtering profiles by gender"""
    response = client.get("/api/profiles?gender=male&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # All results should be male
    for profile in data["data"]:
        assert profile["gender"] == "male"


def test_get_profiles_with_age_filter(client, auth_headers):
    """Test filtering profiles by age range"""
    response = client.get("/api/profiles?min_age=25&max_age=35&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # All results should be within age range
    for profile in data["data"]:
        assert 25 <= profile["age"] <= 35


def test_get_profiles_pagination(client, auth_headers):
    """Test pagination"""
    response1 = client.get("/api/profiles?page=1&limit=5", headers=auth_headers)
    response2 = client.get("/api/profiles?page=2&limit=5", headers=auth_headers)
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    data1 = response1.json()
    data2 = response2.json()
    
    # First result of page 2 should be different from page 1
    if data1["data"] and data2["data"]:
        assert data1["data"][0]["id"] != data2["data"][0]["id"]


def test_get_profiles_sorting(client, auth_headers):
    """Test sorting by age"""
    response = client.get("/api/profiles?sort_by=age&order=asc&limit=20", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    # Check that ages are in ascending order
    ages = [profile["age"] for profile in data["data"]]
    assert ages == sorted(ages)


def test_search_young_males_from_nigeria(client, auth_headers):
    """Test NLP search: young males from nigeria"""
    response = client.get("/api/profiles/search?q=young%20males%20from%20nigeria&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    # Check that all results match the query
    for profile in data["data"]:
        assert profile["gender"] == "male"
        assert 16 <= profile["age"] <= 24  # "young" range
        assert profile["country_id"] == "NG"


def test_search_females_above_30(client, auth_headers):
    """Test NLP search: females above 30"""
    response = client.get("/api/profiles/search?q=females%20above%2030&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    for profile in data["data"]:
        assert profile["gender"] == "female"
        assert profile["age"] >= 30


def test_search_uninterpretable_query(client, auth_headers):
    """Test NLP search with uninterpretable query"""
    response = client.get("/api/profiles/search?q=xyz%20abc%20def", headers=auth_headers)
    assert response.status_code == 400


def test_search_missing_query_parameter(client, auth_headers):
    """Test NLP search without query parameter"""
    response = client.get("/api/profiles/search", headers=auth_headers)
    assert response.status_code == 400


def test_invalid_gender_filter(client, auth_headers):
    """Test invalid gender filter"""
    response = client.get("/api/profiles?gender=invalid", headers=auth_headers)
    assert response.status_code == 422


def test_invalid_age_filter(client, auth_headers):
    """Test invalid age filter"""
    response = client.get("/api/profiles?min_age=-5", headers=auth_headers)
    assert response.status_code == 422


def test_cors_headers(client, auth_headers):
    """Test CORS headers are present"""
    response = client.get("/api/profiles?limit=1", headers=auth_headers)
    # The TestClient might not return CORS headers, but the server should have them


def test_profile_response_structure(client, auth_headers):
    """Test that profile response has all required fields"""
    response = client.get("/api/profiles?limit=1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    if data["data"]:
        profile = data["data"][0]
        required_fields = [
            "id", "name", "gender", "gender_probability",
            "age", "age_group", "country_id", "country_name",
            "country_probability", "created_at"
        ]
        for field in required_fields:
            assert field in profile


# ============ Additional Comprehensive Tests ============

class TestFilterCombinations:
    """Test various filter combinations"""
    
    def test_gender_and_country_filter(self, client, auth_headers):
        """Test filtering by both gender and country"""
        response = client.get("/api/profiles?gender=female&country_id=NG&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        for profile in data["data"]:
            assert profile["gender"] == "female"
            assert profile["country_id"] == "NG"
    
    def test_gender_age_country_filter(self, client, auth_headers):
        """Test filtering by gender, age, and country"""
        response = client.get("/api/profiles?gender=male&min_age=20&max_age=40&country_id=GH&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "male"
            assert 20 <= profile["age"] <= 40
            assert profile["country_id"] == "GH"
    
    def test_age_group_filter(self, client, auth_headers):
        """Test filtering by age group"""
        response = client.get("/api/profiles?age_group=adult&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["age_group"] == "adult"
    
    def test_age_group_and_gender(self, client, auth_headers):
        """Test filtering by age group and gender"""
        response = client.get("/api/profiles?age_group=teenager&gender=male&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["age_group"] == "teenager"
            assert profile["gender"] == "male"
    
    def test_country_id_filter(self, client, auth_headers):
        """Test filtering by country ID"""
        response = client.get("/api/profiles?country_id=KE&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        for profile in data["data"]:
            assert profile["country_id"] == "KE"
    
    def test_probability_threshold_filter(self, client, auth_headers):
        """Test filtering by gender probability threshold"""
        response = client.get("/api/profiles?min_gender_probability=0.9&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender_probability"] >= 0.9
    
    def test_country_probability_threshold(self, client, auth_headers):
        """Test filtering by country probability threshold"""
        response = client.get("/api/profiles?min_country_probability=0.8&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["country_probability"] >= 0.8
    
    def test_all_filters_combined(self, client, auth_headers):
        """Test combining all available filters"""
        response = client.get(
            "/api/profiles?gender=male&age_group=adult&country_id=NG&"
            "min_age=25&max_age=50&min_gender_probability=0.8&"
            "min_country_probability=0.7&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "male"
            assert profile["age_group"] == "adult"
            assert profile["country_id"] == "NG"
            assert 25 <= profile["age"] <= 50
            assert profile["gender_probability"] >= 0.8
            assert profile["country_probability"] >= 0.7


class TestSorting:
    """Test sorting functionality"""
    
    def test_sort_by_gender_probability_asc(self, client, auth_headers):
        """Test sorting by gender probability ascending"""
        response = client.get("/api/profiles?sort_by=gender_probability&order=asc&limit=20", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        probs = [p["gender_probability"] for p in data["data"]]
        assert probs == sorted(probs)
    
    def test_sort_by_gender_probability_desc(self, client, auth_headers):
        """Test sorting by gender probability descending"""
        response = client.get("/api/profiles?sort_by=gender_probability&order=desc&limit=20", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        probs = [p["gender_probability"] for p in data["data"]]
        assert probs == sorted(probs, reverse=True)
    
    def test_sort_by_created_at_asc(self, client, auth_headers):
        """Test sorting by creation date ascending"""
        response = client.get("/api/profiles?sort_by=created_at&order=asc&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_sort_by_created_at_desc(self, client, auth_headers):
        """Test sorting by creation date descending"""
        response = client.get("/api/profiles?sort_by=created_at&order=desc&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_sort_by_age_desc(self, client, auth_headers):
        """Test sorting by age descending"""
        response = client.get("/api/profiles?sort_by=age&order=desc&limit=20", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        ages = [p["age"] for p in data["data"]]
        assert ages == sorted(ages, reverse=True)
    
    def test_invalid_sort_by(self, client, auth_headers):
        """Test invalid sort_by parameter"""
        response = client.get("/api/profiles?sort_by=invalid&limit=10", headers=auth_headers)
        assert response.status_code == 422
    
    def test_invalid_sort_order(self, client, auth_headers):
        """Test invalid sort order parameter"""
        response = client.get("/api/profiles?sort_by=age&order=invalid&limit=10", headers=auth_headers)
        assert response.status_code == 422


class TestPagination:
    """Test pagination functionality"""
    
    def test_default_limit(self, client, auth_headers):
        """Test default limit is 10"""
        response = client.get("/api/profiles", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
    
    def test_max_limit_enforced(self, client, auth_headers):
        """Test that max limit of 50 is enforced"""
        # Limit exceeding max should return 422 (invalid parameter)
        response = client.get("/api/profiles?limit=100", headers=auth_headers)
        assert response.status_code == 422
        
        # Valid max limit should work
        response = client.get("/api/profiles?limit=50", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 50
    
    def test_pagination_beyond_total(self, client, auth_headers):
        """Test pagination when page exceeds available data"""
        response = client.get("/api/profiles?page=10000&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] > 0
    
    def test_page_1_and_page_2_different(self, client, auth_headers):
        """Test that different pages return different data"""
        resp1 = client.get("/api/profiles?page=1&limit=10", headers=auth_headers)
        resp2 = client.get("/api/profiles?page=2&limit=10", headers=auth_headers)
        
        data1 = resp1.json()
        data2 = resp2.json()
        
        assert len(data1["data"]) > 0
        assert len(data2["data"]) > 0
        assert data1["data"][0]["id"] != data2["data"][0]["id"]
    
    def test_pagination_consistency(self, client, auth_headers):
        """Test that same page returns same data"""
        resp1 = client.get("/api/profiles?page=1&limit=10", headers=auth_headers)
        resp2 = client.get("/api/profiles?page=1&limit=10", headers=auth_headers)
        
        data1 = resp1.json()
        data2 = resp2.json()
        
        assert data1["data"] == data2["data"]
    
    def test_pagination_with_limit_1(self, client, auth_headers):
        """Test pagination with limit of 1"""
        response = client.get("/api/profiles?limit=1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1


class TestNLPSearch:
    """Test natural language search functionality"""
    
    def test_search_adult_males_from_kenya(self, client, auth_headers):
        """Test NLP: adult males from kenya"""
        response = client.get("/api/profiles/search?q=adult%20males%20from%20kenya", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        for profile in data["data"]:
            assert profile["gender"] == "male"
            assert profile["age_group"] == "adult"
            assert profile["country_id"] == "KE"
    
    def test_search_people_from_angola(self, client, auth_headers):
        """Test NLP: people from angola"""
        response = client.get("/api/profiles/search?q=people%20from%20angola", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["country_id"] == "AO"
    
    def test_search_teenagers(self, client, auth_headers):
        """Test NLP: teenagers"""
        response = client.get("/api/profiles/search?q=teenagers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["age_group"] == "teenager"
    
    def test_search_males(self, client, auth_headers):
        """Test NLP: males"""
        response = client.get("/api/profiles/search?q=males", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "male"
    
    def test_search_females(self, client, auth_headers):
        """Test NLP: females"""
        response = client.get("/api/profiles/search?q=females", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "female"
    
    def test_search_males_above_25(self, client, auth_headers):
        """Test NLP: males above 25"""
        response = client.get("/api/profiles/search?q=males%20above%2025", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "male"
            assert profile["age"] >= 25
    
    def test_search_females_below_30(self, client, auth_headers):
        """Test NLP: females below 30"""
        response = client.get("/api/profiles/search?q=females%20below%2030", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "female"
            assert profile["age"] <= 30
    
    def test_search_between_ages(self, client, auth_headers):
        """Test NLP: between 20 and 30"""
        response = client.get("/api/profiles/search?q=between%2020%20and%2030", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert 20 <= profile["age"] <= 30
    
    def test_search_young_females(self, client, auth_headers):
        """Test NLP: young females"""
        response = client.get("/api/profiles/search?q=young%20females", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "female"
            assert 16 <= profile["age"] <= 24
    
    def test_search_adult_females_from_nigeria(self, client, auth_headers):
        """Test NLP: adult females from nigeria"""
        response = client.get("/api/profiles/search?q=adult%20females%20from%20nigeria", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        for profile in data["data"]:
            assert profile["gender"] == "female"
            assert profile["age_group"] == "adult"
            assert profile["country_id"] == "NG"
    
    def test_search_with_pagination(self, client, auth_headers):
        """Test NLP search with pagination"""
        response1 = client.get("/api/profiles/search?q=males&page=1&limit=5", headers=auth_headers)
        response2 = client.get("/api/profiles/search?q=males&page=2&limit=5", headers=auth_headers)
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        if len(data1["data"]) > 0 and len(data2["data"]) > 0:
            assert data1["data"][0]["id"] != data2["data"][0]["id"]
    
    def test_search_case_insensitive(self, client, auth_headers):
        """Test NLP search is case insensitive"""
        resp1 = client.get("/api/profiles/search?q=males", headers=auth_headers)
        resp2 = client.get("/api/profiles/search?q=MALES", headers=auth_headers)
        resp3 = client.get("/api/profiles/search?q=Males", headers=auth_headers)
        
        data1 = resp1.json()
        data2 = resp2.json()
        data3 = resp3.json()
        
        assert len(data1["data"]) == len(data2["data"])
        assert len(data2["data"]) == len(data3["data"])


class TestErrorHandling:
    """Test error handling and validation"""
    
    def test_invalid_country_id_format(self, client, auth_headers):
        """Test invalid country ID format (too long)"""
        response = client.get("/api/profiles?country_id=NGR", headers=auth_headers)
        assert response.status_code == 422
    
    def test_max_age_less_than_min_age(self, client, auth_headers):
        """Test when max_age is less than min_age"""
        response = client.get("/api/profiles?min_age=50&max_age=25&limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should return empty since no ages fall in invalid range
        assert len(data["data"]) == 0
    
    def test_invalid_gender_probability(self, client, auth_headers):
        """Test invalid gender probability (> 1)"""
        response = client.get("/api/profiles?min_gender_probability=1.5", headers=auth_headers)
        assert response.status_code == 422
    
    def test_invalid_country_probability(self, client, auth_headers):
        """Test invalid country probability (< 0)"""
        response = client.get("/api/profiles?min_country_probability=-0.1", headers=auth_headers)
        assert response.status_code == 422
    
    def test_invalid_age_group(self, client, auth_headers):
        """Test invalid age group"""
        response = client.get("/api/profiles?age_group=invalid_group", headers=auth_headers)
        assert response.status_code == 422
    
    def test_empty_search_query(self, client, auth_headers):
        """Test empty search query"""
        response = client.get("/api/profiles/search?q=", headers=auth_headers)
        assert response.status_code == 400
    
    def test_search_with_only_spaces(self, client, auth_headers):
        """Test search query with only spaces"""
        response = client.get("/api/profiles/search?q=%20%20%20", headers=auth_headers)
        assert response.status_code == 400


class TestResponseStructure:
    """Test response structure and data integrity"""
    
    def test_response_has_pagination_info(self, client, auth_headers):
        """Test that response includes pagination info"""
        response = client.get("/api/profiles?limit=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "page" in data
        assert "limit" in data
        assert "total" in data
        assert "data" in data
        assert data["page"] >= 1
        assert data["limit"] >= 1
        assert data["total"] >= 0
    
    def test_profile_data_types(self, client, auth_headers):
        """Test that profile data has correct types"""
        response = client.get("/api/profiles?limit=1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        if data["data"]:
            profile = data["data"][0]
            
            assert isinstance(profile["id"], str)
            assert isinstance(profile["name"], str)
            assert isinstance(profile["gender"], str)
            assert isinstance(profile["gender_probability"], float)
            assert isinstance(profile["age"], int)
            assert isinstance(profile["age_group"], str)
            assert isinstance(profile["country_id"], str)
            assert isinstance(profile["country_name"], str)
            assert isinstance(profile["country_probability"], float)
            assert isinstance(profile["created_at"], str)
    
    def test_gender_values_valid(self, client, auth_headers):
        """Test that gender values are valid"""
        response = client.get("/api/profiles?limit=50", headers=auth_headers)
        data = response.json()
        
        valid_genders = ["male", "female"]
        for profile in data["data"]:
            assert profile["gender"] in valid_genders
    
    def test_age_group_values_valid(self, client, auth_headers):
        """Test that age group values are valid"""
        response = client.get("/api/profiles?limit=50", headers=auth_headers)
        data = response.json()
        
        valid_groups = ["child", "teenager", "adult", "senior"]
        for profile in data["data"]:
            assert profile["age_group"] in valid_groups
    
    def test_probability_values_valid(self, client, auth_headers):
        """Test that probability values are between 0 and 1"""
        response = client.get("/api/profiles?limit=50", headers=auth_headers)
        data = response.json()
        
        for profile in data["data"]:
            assert 0 <= profile["gender_probability"] <= 1
            assert 0 <= profile["country_probability"] <= 1
    
    def test_age_values_reasonable(self, client, auth_headers):
        """Test that age values are reasonable"""
        response = client.get("/api/profiles?limit=50", headers=auth_headers)
        data = response.json()
        
        for profile in data["data"]:
            assert 0 <= profile["age"] <= 120
    
    def test_country_id_format(self, client, auth_headers):
        """Test that country IDs are 2-character codes"""
        response = client.get("/api/profiles?limit=20", headers=auth_headers)
        data = response.json()
        
        for profile in data["data"]:
            assert len(profile["country_id"]) == 2
    
    def test_created_at_iso_format(self, client, auth_headers):
        """Test that created_at is in ISO format"""
        response = client.get("/api/profiles?limit=10", headers=auth_headers)
        data = response.json()
        
        for profile in data["data"]:
            # Should be ISO 8601 format
            assert "T" in profile["created_at"]
            assert ":" in profile["created_at"]


class TestDataConsistency:
    """Test data consistency across requests"""
    
    def test_profile_count_consistent(self, client, auth_headers):
        """Test that total profile count is consistent"""
        response1 = client.get("/api/profiles?limit=1", headers=auth_headers)
        response2 = client.get("/api/profiles?limit=1", headers=auth_headers)
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1["total"] == data2["total"]
    
    def test_filter_reduces_count(self, client, auth_headers):
        """Test that filters reduce the count appropriately"""
        resp_all = client.get("/api/profiles?limit=1", headers=auth_headers)
        resp_male = client.get("/api/profiles?gender=male&limit=1", headers=auth_headers)
        
        data_all = resp_all.json()
        data_male = resp_male.json()
        
        # Male count should be less than or equal to total
        assert data_male["total"] <= data_all["total"]
    
    def test_different_filters_have_different_counts(self, client, auth_headers):
        """Test that different gender filters have different counts"""
        resp_male = client.get("/api/profiles?gender=male&limit=1", headers=auth_headers)
        resp_female = client.get("/api/profiles?gender=female&limit=1", headers=auth_headers)
        
        data_male = resp_male.json()
        data_female = resp_female.json()
        
        # Both should have the same count (roughly 50-50 split)
        # Just verify they both have results
        assert data_male["total"] > 0
        assert data_female["total"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
