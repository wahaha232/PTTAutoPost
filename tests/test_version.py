import re

from src.version import BUILD_DATE, CHANGELOG, __version__


def parse(v):
    return tuple(int(x) for x in v.split("."))


def test_changelog_head_matches_version_and_build_date():
    assert CHANGELOG[0][0] == __version__ and CHANGELOG[0][1] == BUILD_DATE
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) and re.fullmatch(r"\d{4}/\d{2}/\d{2}", BUILD_DATE)


def test_changelog_is_newest_first_and_non_empty():
    versions = [parse(v) for v, _d, _n in CHANGELOG]
    assert versions == sorted(versions, reverse=True) and len(set(versions)) == len(versions)
    assert all(notes for _v, _d, notes in CHANGELOG)
    dates = [d for _v, d, _n in CHANGELOG]
    assert dates == sorted(dates, reverse=True)


def test_window_title_shows_the_version(qapp, tmp_path):
    from src.net.session import PttSession
    from src.storage.db import Database
    from src.ui.main_window import MainWindow

    db = Database(tmp_path / "v.db")
    w = MainWindow(db, PttSession())
    assert __version__ in w.windowTitle()
    db.close()
