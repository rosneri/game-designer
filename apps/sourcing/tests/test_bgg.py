import json

from gd_sourcing import bgg
from gd_sourcing.cli import main


def test_clean_desc():
    assert bgg.clean_desc("<p>Players &ldquo;bid&rdquo;\n\n<b>cards</b>.</p>") == "Players “bid” cards."
    assert bgg.clean_desc(None) == ""


def fake_fetch(items: dict[tuple[str, int], dict | None], flaky: set[int] = frozenset()):
    calls = {"n": 0}

    def f(ot, oid, limiter=None):
        calls["n"] += 1
        if oid in flaky:
            raise bgg.Unresolved(f"{ot}/{oid}")
        return items.get((ot, oid))

    return f, calls


def test_scan_resumes_and_skips_unresolved(tmp_path):
    items = {("property", 1): {"objectid": 1, "name": "Card Game", "subtype": "boardgamecategory", "href": "/x",
                               "description": "<p>d</p>", "linkcounts": {"boardgame": 3}, "itemstate": "approved"}}
    f, _calls = fake_fetch(items, flaky={3})
    assert bgg.scan(tmp_path, "properties", 1, 4, workers=2, fetch_fn=f, log=lambda s: None) == 1
    done = set((tmp_path / "raw" / "properties.done").read_text().split())
    assert done == {"1", "2", "4"}  # 3 was unresolved -> retried on the next run
    f2, calls2 = fake_fetch(items)
    bgg.scan(tmp_path, "properties", 1, 4, workers=2, fetch_fn=f2, log=lambda s: None)
    assert calls2["n"] == 1


def test_build_filters_and_groups(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = [
        {"objectid": 1, "name": "Card Game", "subtype": "boardgamecategory", "href": "/c", "description": "", "linkcounts": {"boardgame": 5}, "itemstate": "approved"},
        {"objectid": 2, "name": "Nope", "subtype": "boardgamecategory", "href": "/n", "description": "", "linkcounts": {}, "itemstate": "declined"},
        {"objectid": 3, "name": "Shooter", "subtype": "videogamegenre", "href": "/v", "description": "", "linkcounts": {}, "itemstate": "approved"},
        {"objectid": 4, "name": "Trick-taking", "subtype": "boardgamemechanic", "href": "/m", "description": "<i>x</i>", "linkcounts": {"boardgame": 9}, "itemstate": "approved"},
    ]
    (raw / "properties.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    fams = [
        {"objectid": 10, "name": "Strategy Games", "subtype": "boardgamesubdomain", "href": "/s", "description": "", "linkcounts": {"boardgame": 1}, "itemstate": "approved"},
        {"objectid": 11, "name": "Mechanism: Trick-taking", "subtype": "boardgamefamily", "href": "/f", "description": "", "linkcounts": {"boardgame": 2}, "itemstate": "approved"},
        {"objectid": 12, "name": "Mechanism: Bidding", "subtype": "boardgamefamily", "href": "/f2", "description": "", "linkcounts": {"boardgame": 7}, "itemstate": "approved"},
    ]
    (raw / "families.jsonl").write_text("\n".join(json.dumps(r) for r in fams) + "\n")
    g = bgg.build(tmp_path, log=lambda s: None)
    assert [r["name"] for r in g["categories"]] == ["Card Game"]
    assert g["mechanics"][0]["description"] == "x" and g["subdomains"][0]["name"] == "Strategy Games"
    by_prefix = json.loads((tmp_path / "families_by_prefix.json").read_text())
    assert [r["name"] for r in by_prefix["Mechanism"]] == ["Mechanism: Bidding", "Mechanism: Trick-taking"]
    main(["bgg", "build", "--out", str(tmp_path)])
    assert (tmp_path / "categories.json").exists()
