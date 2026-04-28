"""
Database seeding script for Insighta Labs profiles.
Seeds 2026 demographic profiles from JSON data.
"""

import json
import requests
import sys
from sqlalchemy.exc import IntegrityError
from database import SessionLocal, init_db
from models import Profile
from datetime import datetime
import uuid

# Fix Unicode encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def seed_database():
    """
    Seed the database with profile data from JSON.
    Uses sample data if the Google Drive file is not accessible.
    Re-running this function won't create duplicates due to unique constraint on name.
    """
    init_db()
    db = SessionLocal()

    try:
        # Sample data - in production, this would come from the Google Drive JSON
        sample_profiles = generate_sample_profiles()

        for profile_data in sample_profiles:
            try:
                # Check if profile already exists
                existing = db.query(Profile).filter(Profile.name == profile_data["name"]).first()
                if existing:
                    continue

                profile = Profile(
                    id=uuid.uuid4(),
                    name=profile_data["name"],
                    gender=profile_data["gender"],
                    gender_probability=profile_data["gender_probability"],
                    age=profile_data["age"],
                    age_group=profile_data["age_group"],
                    country_id=profile_data["country_id"],
                    country_name=profile_data["country_name"],
                    country_probability=profile_data["country_probability"],
                )
                db.add(profile)
            except IntegrityError:
                # Profile already exists, skip
                db.rollback()
                continue

        db.commit()
        count = db.query(Profile).count()
        print(f"✓ Database seeded successfully. Total profiles: {count}")

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding database: {str(e)}")
    finally:
        db.close()

def generate_sample_profiles():
    """Load profiles from seed_profiles.json"""
    try:
        with open("seed_profiles.json") as f:
            data = json.load(f)
            # Extract profiles list from JSON structure
            if isinstance(data, dict) and "profiles" in data:
                return data["profiles"]
            elif isinstance(data, list):
                return data
            else:
                raise ValueError("Invalid JSON structure: expected 'profiles' key or array")
    except FileNotFoundError:
        print("seed_profiles.json not found, using generated sample data")
        return


if __name__ == "__main__":
    seed_database()
