"""
Natural Language Query Parser for Profile Filtering

Maps plain English queries to structured filter parameters.
Rule-based parsing only - no LLMs.
"""

import re
from typing import Dict, Optional, Tuple


class QueryParser:
    """
    Rule-based natural language parser for demographic queries.
    
    Supported keywords map to filters:
    - Age: young (16-24), teenager, adult, senior, old
    - Gender: male, female
    - Location: country names or ISO codes
    - Age values: direct numbers or age ranges
    """

    # Age group mappings
    AGE_GROUP_KEYWORDS = {
        "child": "child",
        "children": "child",
        "kid": "child",
        "kids": "child",
        "teenager": "teenager",
        "teen": "teenager",
        "teens": "teenager",
        "adult": "adult",
        "adults": "adult",
        "senior": "senior",
        "seniors": "senior",
        "elderly": "senior",
        "old": "senior",
    }

    # Age range mappings for descriptive terms
    AGE_RANGES = {
        "young": (16, 24),  # young = teenager to early 20s
        "middle-aged": (35, 55),
        "old": (60, 120),
    }

    # Gender mappings
    GENDER_KEYWORDS = {
        "male": "male",
        "males": "male",
        "man": "male",
        "men": "male",
        "boy": "male",
        "boys": "male",
        "female": "female",
        "females": "female",
        "woman": "female",
        "women": "female",
        "girl": "female",
        "girls": "female",
        "lady": "female",
        "ladies": "female",
    }

    # Country mappings (sample - can be extended)
    COUNTRY_MAPPINGS = {
        "nigeria": "NG",
        "nigerian": "NG",
        "benin": "BJ",
        "beninese": "BJ",
        "ghana": "GH",
        "ghanaian": "GH",
        "kenya": "KE",
        "kenyan": "KE",
        "uganda": "UG",
        "ugandan": "UG",
        "tanzania": "TZ",
        "tanzanian": "TZ",
        "south africa": "ZA",
        "south african": "ZA",
        "egypt": "EG",
        "egyptian": "EG",
        "ethiopia": "ET",
        "ethiopian": "ET",
        "cameroon": "CM",
        "cameroonian": "CM",
        "angola": "AO",
        "angolan": "AO",
        "mozambique": "MZ",
        "mozambican": "MZ",
        "zimbabwe": "ZW",
        "zimbabwean": "ZW",
        "zambia": "ZM",
        "zambian": "ZM",
        "malawi": "MW",
        "malawian": "MW",
        "botswana": "BW",
        "batswana": "BW",
    }

    @classmethod
    def parse(cls, query: str) -> Tuple[bool, Optional[Dict]]:
        """
        Parse a natural language query into filter parameters.
        
        Returns:
            (success: bool, filters: Dict or None)
            - If success is True, filters contains the parsed parameters
            - If success is False, filters is None
        """
        if not query or not query.strip():
            return False, None

        query_lower = query.lower().strip()
        filters = {}

        # Extract numbers and age ranges
        age_values = cls._extract_ages(query_lower)
        if age_values:
            filters.update(age_values)

        # Extract gender
        gender = cls._extract_gender(query_lower)
        if gender:
            filters["gender"] = gender

        # Extract age group
        age_group = cls._extract_age_group(query_lower)
        if age_group:
            filters["age_group"] = age_group

        # Extract country
        country = cls._extract_country(query_lower)
        if country:
            filters["country_id"] = country

        # If we found at least one filter, return success
        if filters:
            return True, filters

        # No interpretable keywords found
        return False, None

    @classmethod
    def _extract_ages(cls, query: str) -> Dict:
        """Extract age values from query"""
        filters = {}

        # Look for "above X", "over X", "older than X", "> X"
        above_pattern = r"(?:above|over|older than|>)\s*(\d+)"
        above_match = re.search(above_pattern, query)
        if above_match:
            filters["min_age"] = int(above_match.group(1))

        # Look for "below X", "under X", "younger than X", "< X"
        below_pattern = r"(?:below|under|younger than|<)\s*(\d+)"
        below_match = re.search(below_pattern, query)
        if below_match:
            filters["max_age"] = int(below_match.group(1))

        # Look for "between X and Y"
        between_pattern = r"between\s*(\d+)\s*and\s*(\d+)"
        between_match = re.search(between_pattern, query)
        if between_match:
            filters["min_age"] = int(between_match.group(1))
            filters["max_age"] = int(between_match.group(2))

        # Look for direct age or age range (e.g., "25 year old", "20-30")
        # Only if we haven't already found above/below/between
        if not filters:
            age_pattern = r"(\d+)(?:\s*-\s*(\d+))?"
            for match in re.finditer(age_pattern, query):
                age1 = int(match.group(1))
                age2 = int(match.group(2)) if match.group(2) else None
                
                if age2:
                    filters["min_age"] = age1
                    filters["max_age"] = age2
                    break

        # Check for age range keywords (young, old, etc.)
        for keyword, (min_age, max_age) in cls.AGE_RANGES.items():
            if keyword in query:
                # Only add if not already set
                if "min_age" not in filters:
                    filters["min_age"] = min_age
                if "max_age" not in filters:
                    filters["max_age"] = max_age
                break

        return filters

    @classmethod
    def _extract_gender(cls, query: str) -> Optional[str]:
        """Extract gender from query - prioritizes longer keywords to avoid substring matches"""
        # Sort keywords by length (longest first) to match longer words before shorter substrings
        sorted_keywords = sorted(cls.GENDER_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True)
        for keyword, gender in sorted_keywords:
            if keyword in query:
                return gender
        return None

    @classmethod
    def _extract_age_group(cls, query: str) -> Optional[str]:
        """Extract age group from query - prioritizes longer keywords"""
        # Sort keywords by length (longest first) to avoid substring matches
        sorted_keywords = sorted(cls.AGE_GROUP_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True)
        for keyword, age_group in sorted_keywords:
            if keyword in query:
                return age_group
        return None

    @classmethod
    def _extract_country(cls, query: str) -> Optional[str]:
        """Extract country from query - prioritizes longer keywords"""
        # Sort keywords by length (longest first) to avoid substring matches
        sorted_keywords = sorted(cls.COUNTRY_MAPPINGS.items(), key=lambda x: len(x[0]), reverse=True)
        for keyword, country_code in sorted_keywords:
            if keyword in query:
                return country_code
        return None
