import json

from app.services.apple_catalog_service import AppleCatalogService


def test_search_falls_back_to_tw_then_hk_without_us(monkeypatch) -> None:
    """当前地区候选不足时应按台湾、香港补充，且不得查询美国区。"""
    service = AppleCatalogService()
    calls: list[str] = []
    results = {
        "cn": [{"apple_id": "1", "title": "七里香 (女声版)", "artist": "翻唱歌手"}],
        "tw": [{"apple_id": "2", "title": "七里香", "artist": "周杰伦"}],
        "hk": [{"apple_id": "3", "title": "七里香", "artist": "周杰伦"}],
    }

    def fake_search_storefront(keyword: str, country: str) -> list[dict]:
        calls.append(country)
        return results[country]

    monkeypatch.setattr(service, "_search_storefront", fake_search_storefront)

    candidates = service.search("七里香", country="cn", limit=8)

    assert calls == ["cn", "tw", "hk"]
    assert [item["apple_id"] for item in candidates] == ["2", "1"]


def test_search_stops_when_current_storefront_has_enough_results(monkeypatch) -> None:
    """当前地区已有足量结果时，不应继续请求回退地区。"""
    service = AppleCatalogService()
    calls: list[str] = []
    local_results = [
        {"apple_id": str(index), "title": f"歌曲{index}", "artist": "歌手"}
        for index in range(8)
    ]

    def fake_search_storefront(keyword: str, country: str) -> list[dict]:
        calls.append(country)
        return local_results

    monkeypatch.setattr(service, "_search_storefront", fake_search_storefront)

    assert len(service.search("测试", country="cn", limit=8)) == 8
    assert calls == ["cn"]


def test_extracts_song_candidates_from_apple_music_page() -> None:
    """应从 Apple Music 网页序列化数据提取歌曲候选。"""
    service = AppleCatalogService()
    payload = {
        "data": [
            {
                "id": "square-section - album - 536114662",
                "titleLinks": [{"title": "七里香"}],
            },
            {
                "itemKind": "songs",
                "title": "七里香",
                "subtitle": "歌曲 · 周杰伦",
                "artwork": {"dictionary": {"url": "https://example.com/{w}x{h}.{f}"}},
                "contentDescriptor": {
                    "kind": "song",
                    "identifiers": {"storeAdamID": "536115195"},
                    "url": "https://music.apple.com/cn/album/七里香/536114662?i=536115195",
                },
            },
        ],
    }
    page = (
        '<script type="application/json" id="serialized-server-data">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )

    assert service._extract_results(page, "cn") == [{
        "apple_id": "536115195",
        "title": "七里香",
        "artist": "周杰伦",
        "album": "七里香",
        "duration_ms": 0,
        "artwork_url": "https://example.com/200x200.jpg",
        "track_url": "https://music.apple.com/cn/album/七里香/536114662?i=536115195",
        "country": "cn",
    }]
