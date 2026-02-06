from __future__ import annotations

# Contract constants should be versioned and adjusted as the domain evolves.

CANONICAL_LISTING_REQUIRED_FIELDS = [
    "id",
    "source_id",
    "external_id",
    "url",
    "title",
    "price",
    "surface_area_sqm",
    "property_type",
]

# Fields that should generally be present for "valid" normalized listings.
CANONICAL_LISTING_KEY_FIELDS = [
    "bedrooms",
    "bathrooms",
    "location",
]
