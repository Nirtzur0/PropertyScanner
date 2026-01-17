from dataclasses import dataclass
import re
import unicodedata
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import structlog

from src.listings.services.geocoding_service import GeocodingService
from src.platform.utils.config import ConfigLoader

logger = structlog.get_logger(__name__)


_PATH_PREFIXES: Dict[str, List[str]] = {
    "idealista": [
        "/venta-viviendas",
        "/alquiler-viviendas",
        "/venta-obra-nueva",
        "/alquiler-obra-nueva",
    ],
    "pisos": ["/venta/", "/alquiler/", "/comprar/"],
    "rightmove_uk": ["/property-for-sale", "/property-to-rent", "/properties/"],
    "zoopla_uk": ["/for-sale", "/to-rent", "/details/"],
    "immobiliare_it": ["/vendita-case", "/affitto-case", "/annunci/"],
}

_COUNTRY_HINTS = {
    "spain": "ES",
    "espana": "ES",
    "espa": "ES",
    "uk": "GB",
    "united kingdom": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "italy": "IT",
    "italia": "IT",
}


@dataclass(frozen=True)
class CrawlTarget:
    source_id: str
    search_path: str
    reason: str


class SourceRouter:
    """
    Resolve a location/search hint into a source_id + search path/URL.
    Keeps routing deterministic and config-driven.
    """

    def __init__(
        self,
        config_loader: Optional[ConfigLoader] = None,
        geocoder: Optional[GeocodingService] = None,
    ) -> None:
        self.config_loader = config_loader or ConfigLoader()
        self.sources = self.config_loader.sources.sources
        self.geocoder = geocoder or GeocodingService()
        self._geo_cache: Dict[str, Optional[str]] = {}

        self.base_url_by_id: Dict[str, str] = {}
        self.domain_map: Dict[str, str] = {}
        self.country_sources: Dict[str, List[str]] = {}
        self.search_path_templates: Dict[str, str] = {}
        self.search_url_templates: Dict[str, str] = {}

        for source in self.sources:
            source_id = source.id
            if not source_id:
                continue
            base_url = source.base_url or ""
            if base_url:
                self.base_url_by_id[source_id] = base_url
                parsed = urlparse(base_url)
                if parsed.netloc:
                    self.domain_map[parsed.netloc.lower()] = source_id

            for country in source.countries or []:
                code = str(country).upper()
                self.country_sources.setdefault(code, []).append(source_id)

            if source.search_path_template:
                self.search_path_templates[source_id] = source.search_path_template
            if source.search_url_template:
                self.search_url_templates[source_id] = source.search_url_template

        # Domain aliases that do not appear in config base_url values.
        self.domain_map.setdefault("idealista.es", "idealista")
        self.domain_map.setdefault("www.idealista.es", "idealista")
        self.domain_map.setdefault("rightmove.co.uk", "rightmove_uk")
        self.domain_map.setdefault("zoopla.co.uk", "zoopla_uk")
        self.domain_map.setdefault("immobiliare.it", "immobiliare_it")
        self.domain_map.setdefault("pisos.com", "pisos")

    def resolve(self, area: str) -> List[CrawlTarget]:
        if not area or not str(area).strip():
            return []

        raw = str(area).strip()
        normalized_url = self._normalize_url(raw)
        if normalized_url:
            target = self._resolve_url(normalized_url)
            return [target] if target else []

        if "/" in raw:
            path = raw if raw.startswith("/") else f"/{raw}"
            target = self._resolve_path(path)
            if target:
                return [target]

        return self._resolve_location(raw)

    def _normalize_url(self, value: str) -> Optional[str]:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value

        for domain in self.domain_map.keys():
            if domain in value:
                if value.startswith("http"):
                    return value
                return f"https://{value.lstrip('/')}"

        return None

    def _resolve_url(self, url: str) -> Optional[CrawlTarget]:
        parsed = urlparse(url)
        source_id = self.domain_map.get(parsed.netloc.lower())
        if not source_id:
            logger.warning("source_router_unknown_domain", url=url, domain=parsed.netloc)
            return None

        if source_id == "idealista":
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return CrawlTarget(source_id=source_id, search_path=path, reason="url_domain")

        return CrawlTarget(source_id=source_id, search_path=url, reason="url_domain")

    def _resolve_path(self, path: str) -> Optional[CrawlTarget]:
        source_id = self._match_path_source(path)
        if not source_id:
            return None

        if source_id == "idealista":
            return CrawlTarget(source_id=source_id, search_path=path, reason="path_prefix")

        base_url = self.base_url_by_id.get(source_id, "")
        if base_url:
            return CrawlTarget(
                source_id=source_id,
                search_path=urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
                reason="path_prefix",
            )

        return CrawlTarget(source_id=source_id, search_path=path, reason="path_prefix")

    def _resolve_location(self, location: str) -> List[CrawlTarget]:
        country_code = self._country_for_location(location)
        if not country_code:
            logger.warning("source_router_country_unknown", location=location)
            return []

        sources = self.country_sources.get(country_code, [])
        targets: List[CrawlTarget] = []
        for source_id in sources:
            search_path = self._build_search_path(source_id, location)
            if not search_path:
                continue
            targets.append(
                CrawlTarget(
                    source_id=source_id,
                    search_path=search_path,
                    reason=f"country:{country_code}",
                )
            )

        if not targets:
            logger.warning("source_router_no_templates", location=location, country=country_code)
        return targets

    def _match_path_source(self, path: str) -> Optional[str]:
        lower = path.lower()
        for source_id, prefixes in _PATH_PREFIXES.items():
            for prefix in prefixes:
                if lower.startswith(prefix):
                    return source_id
        return None

    def _build_search_path(self, source_id: str, location: str) -> Optional[str]:
        slug = self._slugify(location)
        if not slug:
            return None

        if source_id in self.search_path_templates:
            template = self.search_path_templates[source_id]
            path = template.format(slug=slug)
            return path

        if source_id in self.search_url_templates:
            template = self.search_url_templates[source_id]
            url = template.format(slug=slug)
            if url.startswith("/"):
                base_url = self.base_url_by_id.get(source_id, "")
                if base_url:
                    return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
            return url

        return None

    def _country_for_location(self, location: str) -> Optional[str]:
        key = location.strip().lower()
        if key in self._geo_cache:
            return self._geo_cache[key]

        for hint, code in _COUNTRY_HINTS.items():
            if hint in key:
                self._geo_cache[key] = code
                return code

        try:
            details = self.geocoder.geocode_details(location)
            country_code = (details or {}).get("country_code")
            if country_code:
                country_code = country_code.upper()
        except Exception as exc:
            logger.warning("source_router_geocode_failed", location=location, error=str(exc))
            country_code = None

        self._geo_cache[key] = country_code
        return country_code

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
        return slug
