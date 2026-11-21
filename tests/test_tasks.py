from src import sites
from src.ui import tasks


def test_update_check_cancel_suppresses_the_result(qapp, monkeypatch):
    monkeypatch.setattr(tasks.update, "fetch_latest_release", lambda _token: object())
    cancelled = tasks.UpdateCheckTask(None)
    seen = []
    cancelled.signals.done.connect(seen.append)
    cancelled.cancel()
    cancelled.run()
    assert seen == []

    normal = tasks.UpdateCheckTask(None)
    result = object()
    monkeypatch.setattr(tasks.update, "fetch_latest_release", lambda _token: result)
    normal.signals.done.connect(seen.append)
    normal.run()
    assert seen == [result]


def test_site_check_cancel_suppresses_the_result(qapp, monkeypatch):
    result = sites.SiteCheck(sites.SiteStage.TCP_OK, True, "TCP 可連線")
    monkeypatch.setattr(tasks.sites, "check_site_detailed", lambda _site: result)
    cancelled = tasks.SiteCheckTask({})
    seen = []
    cancelled.signals.done.connect(lambda ok, msg: seen.append((ok, msg)))
    cancelled.cancel()
    cancelled.run()
    assert seen == []

    normal = tasks.SiteCheckTask({})
    normal.signals.done.connect(lambda ok, msg: seen.append((ok, msg)))
    normal.run()
    assert seen == [(True, "TCP 可連線")]
