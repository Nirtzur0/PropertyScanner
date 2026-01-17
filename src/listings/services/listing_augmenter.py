from typing import Iterable, List

from src.platform.domain.schema import CanonicalListing
from src.platform.config import DEFAULT_DB_URL
from src.listings.services.enrichment_service import EnrichmentService
from src.valuation.services.rent_estimator import RentEstimator


class ListingAugmentor:
    def __init__(self, db_url: str = DEFAULT_DB_URL):
        self.enrichment = EnrichmentService()
        self.rent_estimator = RentEstimator(db_url)

    def augment_listing(
        self,
        listing: CanonicalListing,
        *,
        enrich_city: bool = True,
        estimate_rent: bool = True,
    ) -> CanonicalListing:
        if enrich_city and listing.location and listing.location.lat and listing.location.lon:
            if not listing.location.city or listing.location.city == "Unknown":
                city = self.enrichment.get_city(listing.location.lat, listing.location.lon)
                if city and city != "Unknown":
                    listing.location.city = city

        if estimate_rent and listing.listing_type == "sale" and listing.price and listing.price > 0:
            rent = self.rent_estimator.estimate_rent(listing)
            if rent:
                listing.estimated_rent = rent
                listing.gross_yield = self.rent_estimator.calculate_yield(listing.price, rent)

        return listing

    def augment_listings(
        self,
        listings: Iterable[CanonicalListing],
        *,
        enrich_city: bool = True,
        estimate_rent: bool = True,
    ) -> List[CanonicalListing]:
        return [
            self.augment_listing(listing, enrich_city=enrich_city, estimate_rent=estimate_rent)
            for listing in listings
        ]
