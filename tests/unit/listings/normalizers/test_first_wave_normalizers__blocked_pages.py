from datetime import datetime

import pytest

from src.listings.agents.processors.immowelt import ImmoweltNormalizerAgent
from src.listings.agents.processors.realtor import RealtorNormalizerAgent
from src.listings.agents.processors.redfin import RedfinNormalizerAgent
from src.listings.agents.processors.seloger import SeLogerNormalizerAgent
from src.platform.domain.schema import RawListing


@pytest.mark.parametrize(
    ("agent_cls", "source_id"),
    [
        (RealtorNormalizerAgent, "realtor_us"),
        (RedfinNormalizerAgent, "redfin_us"),
        (SeLogerNormalizerAgent, "seloger_fr"),
        (ImmoweltNormalizerAgent, "immowelt_de"),
    ],
)
def test_first_wave_normalizers__challenge_page__surfaces_blocked(agent_cls, source_id) -> None:
    raw = RawListing(
        source_id=source_id,
        external_id="blocked-1",
        url=f"https://example.com/{source_id}/blocked-1",
        raw_data={"html_snippet": "<html><script src='https://js.datadome.co/tags.js'></script></html>"},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    response = agent_cls().run({"raw_listings": [raw]})

    assert response.status == "blocked"
    assert response.data == []
    assert response.errors == [f"blocked:datadome_captcha:{raw.url}"]
