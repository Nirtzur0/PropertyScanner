from __future__ import annotations

import hashlib
import os
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import instructor
from litellm import completion
from pydantic import BaseModel, Field
import structlog

from src.platform.domain.schema import (
    CanonicalListing,
    RawListing,
    PropertyType,
    Currency,
    ListingStatus,
    GeoLocation,
)
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


class LLMListingExtract(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    listing_type: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    surface_area_sqm: Optional[float] = None
    floor: Optional[int] = None
    has_elevator: Optional[bool] = None
    address_full: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    image_urls: Optional[List[str]] = Field(default_factory=list)


class LLMNormalizerService:
    def __init__(self, *, app_config: Optional[AppConfig] = None) -> None:
        self.app_config = app_config or load_app_config_safe()
        llm_cfg = self.app_config.llm
        self.models = [m.strip() for m in llm_cfg.text_models if m and str(m).strip()]
        self.temperature = llm_cfg.temperature
        self.max_tokens = llm_cfg.max_tokens
        self.timeout_seconds = llm_cfg.timeout_seconds
        self.max_chars = llm_cfg.normalizer_max_chars
        self.api_base = llm_cfg.api_base
        self.api_key_env = llm_cfg.api_key_env
        self.client = instructor.from_litellm(completion)

    def extract(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet") or ""
        if not html:
            return None
        if not self.models:
            return None

        text = self._html_to_text(html)
        if not text:
            return None

        payload = self._truncate(text)
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract listing details from the HTML text. "
                    "Return only the fields in the response model. "
                    "Use null when unknown. Currency should be ISO (EUR, GBP, USD). "
                    "listing_type should be sale or rent."
                ),
            },
            {
                "role": "user",
                "content": f"Source: {raw.source_id}\nURL: {raw.url}\nHTML:\n{payload}",
            },
        ]

        last_error: Optional[str] = None
        for model in self.models:
            try:
                request_kwargs = {
                    "model": model,
                    "messages": messages,
                    "response_model": LLMListingExtract,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "timeout": self.timeout_seconds,
                    "api_base": self.api_base,
                }
                api_key = os.environ.get(self.api_key_env, "").strip() if self.api_key_env else ""
                if api_key:
                    request_kwargs["api_key"] = api_key
                result = self.client.chat.completions.create(
                    **request_kwargs,
                )
                listing = self._to_canonical(raw, result, model)
                if listing is None:
                    continue
                return listing
            except Exception as exc:
                last_error = str(exc)
                logger.warning("llm_normalizer_failed", model=model, error=last_error)

        if last_error:
            logger.warning("llm_normalizer_exhausted", error=last_error)
        return None

    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def _truncate(self, text: str) -> str:
        if self.max_chars <= 0:
            return text
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars]

    def _to_canonical(
        self,
        raw: RawListing,
        extract: LLMListingExtract,
        model: str,
    ) -> Optional[CanonicalListing]:
        price = extract.price or 0.0
        if price <= 0:
            return None

        title = extract.title or "Unknown Property"
        description = extract.description

        currency = self._normalize_currency(extract.currency, raw.url)
        listing_type = self._normalize_listing_type(extract.listing_type)
        property_type = self._normalize_property_type(extract.property_type)

        address_full = extract.address_full or title
        city = extract.city or "Unknown"
        country = self._normalize_country(extract.country, raw.url, raw.source_id)

        location = GeoLocation(
            lat=extract.lat,
            lon=extract.lon,
            address_full=address_full,
            city=city,
            country=country,
        )

        image_urls = self._normalize_image_urls(extract.image_urls or [])

        unique_hash = hashlib.md5(f"{raw.source_id}:{raw.external_id}".encode()).hexdigest()
        return CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            description=description,
            price=float(price),
            currency=currency,
            listing_type=listing_type,
            property_type=property_type,
            bedrooms=extract.bedrooms,
            bathrooms=extract.bathrooms,
            surface_area_sqm=extract.surface_area_sqm,
            floor=extract.floor,
            has_elevator=extract.has_elevator,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            location=location,
            analysis_meta={
                "llm_normalizer": True,
                "llm_model": model,
            },
        )

    def _normalize_currency(self, value: Optional[str], url: str) -> Currency:
        if value:
            text = str(value).upper()
            if "EUR" in text or "€" in text:
                return Currency.EUR
            if "GBP" in text or "£" in text:
                return Currency.GBP
            if "USD" in text or "$" in text:
                return Currency.USD

        host = urlparse(str(url or "")).netloc.lower()
        if host.endswith(".co.uk") or ".co.uk" in host:
            return Currency.GBP
        return Currency.EUR

    def _normalize_listing_type(self, value: Optional[str]) -> str:
        if not value:
            return "sale"
        text = str(value).strip().lower()
        if "rent" in text or "alquiler" in text or "lease" in text:
            return "rent"
        return "sale"

    def _normalize_property_type(self, value: Optional[str]) -> PropertyType:
        if not value:
            return PropertyType.OTHER
        text = str(value).strip().lower()
        if "apartment" in text or "flat" in text or "piso" in text:
            return PropertyType.APARTMENT
        if "house" in text or "villa" in text or "casa" in text:
            return PropertyType.HOUSE
        if "land" in text or "plot" in text or "terreno" in text:
            return PropertyType.LAND
        if "commercial" in text or "office" in text or "retail" in text:
            return PropertyType.COMMERCIAL
        return PropertyType.OTHER

    def _normalize_country(self, value: Optional[str], url: str, source_id: str) -> str:
        if value:
            text = str(value).strip().upper()
            if len(text) == 2:
                return text
        host = urlparse(str(url or "")).netloc.lower()
        if host.endswith(".co.uk") or ".co.uk" in host or "uk" in source_id.lower():
            return "GB"
        if ".it" in host or "italy" in source_id.lower():
            return "IT"
        if ".es" in host or "spain" in source_id.lower():
            return "ES"
        if ".pt" in host or "portugal" in source_id.lower():
            return "PT"
        if ".de" in host or "germany" in source_id.lower():
            return "DE"
        if ".fr" in host or "france" in source_id.lower():
            return "FR"
        return "ES"

    def _normalize_image_urls(self, urls: List[str]) -> List[str]:
        normalized: List[str] = []
        for url in urls:
            try:
                parsed = urlparse(str(url))
            except Exception:
                continue
            if parsed.scheme not in ("http", "https"):
                continue
            if not parsed.netloc:
                continue
            normalized.append(str(url))
        return normalized
