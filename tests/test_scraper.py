import pytest

from manhwa.config import load_config
from manhwa.ingest.scraper import (
    chapter_dirname,
    chapter_number,
    page_stem,
    parse_selection,
    site_profile,
    unique_chapters,
)


@pytest.mark.parametrize("url, text, expected", [
    ("https://site.com/series/solo-123/chapter/12", "", 12.0),
    ("https://site.com/series/solo-123/chapter-12-5", "", 12.5),
    ("https://site.com/read/abc", "Chapter 7", 7.0),
    ("https://site.com/manga/x/chapitre-3", "", 3.0),
    ("https://site.com/series/solo-123", "Bookmark", None),
])
def test_chapter_number(url, text, expected):
    assert chapter_number(url, text) == expected


def test_unique_chapters_sorts_numerically_and_dedupes():
    links = [
        ("https://s.com/x/chapter/100", "Chapter 100"),
        ("https://s.com/x/chapter/2", "Chapter 2"),
        ("https://s.com/x/chapter/10", "Chapter 10"),
        ("https://s.com/x/chapter/1", "First chapter"),
        ("https://s.com/x/chapter/1", "Chapter 1"),
        ("https://s.com/x", "Home"),
    ]
    assert [n for n, _ in unique_chapters(links)] == [1, 2, 10, 100]


def test_parse_selection():
    numbers = [1, 2, 3, 4, 5, 8, 10, 12.5]
    assert parse_selection("", numbers) == [1]
    assert parse_selection("latest", numbers) == [12.5]
    assert parse_selection("all", numbers) == numbers
    assert parse_selection("2-4,8", numbers) == [2, 3, 4, 8]
    assert parse_selection("10-20", numbers) == [10, 12.5]
    with pytest.raises(ValueError):
        parse_selection("abc", numbers)


def test_names_sort_in_reading_order():
    assert chapter_dirname(12.0) == "chapter-012"
    assert chapter_dirname(12.5) == "chapter-012.5"
    stems = [page_stem(i, 120) for i in (1, 11, 100, 120)]
    assert stems == sorted(stems) == ["001", "011", "100", "120"]


def test_site_profile_falls_back_to_default():
    cfg = load_config()
    cfg["scraper"]["sites"]["other"] = {"domains": ["other.example"], "title": "h1"}
    assert site_profile(cfg, "https://unknown.example/x")[0] == "default"
    name, profile = site_profile(cfg, "https://www.other.example/series/x")
    assert name == "other"
    assert profile["title"] == "h1"
    assert profile["chapter_links"] == cfg["scraper"]["sites"]["default"]["chapter_links"]
