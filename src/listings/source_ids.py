from __future__ import annotations

from typing import Dict, Iterable, List, Set


_CANONICAL_ALIASES: Dict[str, Set[str]] = {
    "pisos": {"pisos"},
    "idealista": {"idealista"},
    "idealista_it": {"idealista_it"},
    "idealista_pt": {"idealista_pt"},
    "rightmove_uk": {"rightmove_uk", "rightmove"},
    "zoopla_uk": {"zoopla_uk", "zoopla"},
    "onthemarket_uk": {"onthemarket_uk", "onthemarket"},
    "immobiliare_it": {"immobiliare_it", "immobiliare"},
    "casa_it": {"casa_it"},
    "seloger_fr": {"seloger_fr", "seloger"},
    "funda_nl": {"funda_nl", "funda"},
    "pararius_nl": {"pararius_nl", "pararius"},
    "immowelt_de": {"immowelt_de", "immowelt"},
    "imovirtual_pt": {"imovirtual_pt", "imovirtual"},
    "daft_ie": {"daft_ie", "daft"},
    "sreality_cz": {"sreality_cz", "sreality"},
    "otodom_pl": {"otodom_pl"},
    "realtor_us": {"realtor_us", "realtor"},
    "redfin_us": {"redfin_us", "redfin"},
    "homes_us": {"homes_us", "homes"},
}

_ALIAS_TO_CANONICAL: Dict[str, str] = {
    alias: canonical
    for canonical, aliases in _CANONICAL_ALIASES.items()
    for alias in aliases
}


def canonicalize_source_id(source_id: str | None) -> str:
    value = str(source_id or "").strip()
    if not value:
        return value
    return _ALIAS_TO_CANONICAL.get(value, value)


def source_aliases(source_id: str | None) -> Set[str]:
    canonical = canonicalize_source_id(source_id)
    if not canonical:
        return set()
    return set(_CANONICAL_ALIASES.get(canonical, {canonical}))


def matches_source_alias(source_id: str | None, candidate: str | None) -> bool:
    if not source_id or not candidate:
        return False
    return canonicalize_source_id(source_id) == canonicalize_source_id(candidate)


def canonical_source_map(source_ids: Iterable[str]) -> Dict[str, str]:
    return {str(source_id): canonicalize_source_id(str(source_id)) for source_id in source_ids}


def canonical_source_ids(source_ids: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for source_id in source_ids:
        canonical = canonicalize_source_id(str(source_id))
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        ordered.append(canonical)
    return ordered
