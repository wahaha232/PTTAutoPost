from src import pttmoney


def test_normal_article_estimate():
    est = pttmoney.estimate("閒聊", "測試" * 100)          # 200 valid chars
    assert est.chars == 200 and est.points == 50 and est.seconds == 100
    assert not est.capped and not est.news and est.cap == 1000


def test_news_title_cap_is_5_points():
    est = pttmoney.estimate("[新聞] 標題", "字" * 200)      # raw 50 P
    assert est.news and est.cap == 5 and est.points == 5 and est.capped


def test_normal_cap_is_1000_points():
    est = pttmoney.estimate("標題", "字" * 5000)            # raw 1250 P
    assert est.points == 1000 and est.capped and est.cap == 1000


def test_whitespace_and_control_are_not_counted():
    assert pttmoney.valid_chars("a b\n\tc　d") == 4
    assert pttmoney.valid_chars("") == 0


def test_fast_and_money_modes_are_estimated_separately():
    body = "字" * 1000
    fast = pttmoney.estimate("閒聊", body, "fast")
    money = pttmoney.estimate("閒聊", body, "money")
    assert money.points == 250 and fast.points < money.points
    assert fast.seconds < money.seconds


def test_duration_formatting():
    assert pttmoney.format_duration(0.3) == "不到 1 秒"
    assert pttmoney.format_duration(50) == "50 秒"
    assert pttmoney.format_duration(130) == "2 分 10 秒"
    assert pttmoney.format_duration(3700) == "1 小時 1 分"
