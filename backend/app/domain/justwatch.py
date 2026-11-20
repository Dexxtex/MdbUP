"""Stable JustWatch provider catalogue used by seed and live verification.

The public endpoint identifies a package by ``shortName`` and ``technicalName``.
The mapping below was verified live against ``packages(country: IT, platform:
WEB)`` on 2026-11-18. It is static reference data, not a substitute for the
periodic ``justwatch-collections`` verification: the CLI still re-checks every
package and updates the persisted mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

MAPPING_VERIFIED_AT = "2026-11-18"


@dataclass(frozen=True)
class JustWatchProviderMapping:
    slug: str
    short_name: str
    technical_name: str
    monetization_types: tuple[str, ...]


PROVIDER_MAPPINGS: tuple[JustWatchProviderMapping, ...] = (
    JustWatchProviderMapping("netflix", "nfx", "netflix", ("FLATRATE",)),
    JustWatchProviderMapping("prime-video", "prv", "amazonprimevideo", ("FLATRATE", "FREE")),
    JustWatchProviderMapping("disney-plus", "dnp", "disneyplus", ("FLATRATE",)),
    JustWatchProviderMapping("apple-tv-plus", "atp", "appletvplus", ("FLATRATE", "FREE")),
    JustWatchProviderMapping("now", "ntv", "nowtv", ("FLATRATE", "FREE")),
    JustWatchProviderMapping("paramount-plus", "pmp", "paramountplus", ("FLATRATE", "FREE")),
    JustWatchProviderMapping("raiplay", "rai", "raiplay", ("ADS", "FLATRATE", "FREE")),
    JustWatchProviderMapping(
        "mediaset-infinity", "msp", "mediasetplay", ("ADS", "FLATRATE", "FREE")
    ),
    JustWatchProviderMapping("infinity-plus", "inf", "infinity", ("FLATRATE",)),
    JustWatchProviderMapping("timvision", "tvi", "timvision", ("BUY", "FLATRATE", "RENT")),
    # Verified, but no FLATRATE: it stays visible as a provider without a
    # subscription catalogue.
    JustWatchProviderMapping("rakuten-tv", "wki", "wuaki", ("ADS", "BUY", "RENT")),
    JustWatchProviderMapping("mubi", "mbi", "mubi", ("FLATRATE",)),
)

MAPPING_BY_SLUG = {mapping.slug: mapping for mapping in PROVIDER_MAPPINGS}
