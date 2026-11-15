"""Article-reading helpers: pmore footer, same-id push merging, wheel limits and the back arrow."""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QWheelEvent

from src.net.session import PttSession
from src.terminal.reading import merged_push_rows, reading_state
from src.terminal.screen import Screen
from src.ui.terminal_widget import TerminalWidget

FOOTER_MID = "  瀏覽 第 1/3 頁 ( 32%)  目前顯示: 第 01~22 行  (y)回應(X%)推文(h)說明(←)離開 "
FOOTER_MORE = "  瀏覽 第 2/3 頁 ( 66%)  目前顯示: 第 23~44 行  (y)回應(X%)推文(h)說明(←)離開 "
FOOTER_END = "  瀏覽 第 3/3 頁 (100%)  目前顯示: 第 45~66 行  (y)回應(X%)推文(h)說明(←)離開 "


def screen_with(lines, footer=""):
    s = Screen()
    body = "\r\n".join(lines)
    s.feed(body.encode("cp950"))
    if footer:
        s.feed(f"\x1b[{s.rows};1H{footer}".encode("cp950"))
    return s


def test_reading_state_from_pmore_footer():
    assert reading_state(screen_with(["hello"])) is None
    top = reading_state(screen_with(["x"], FOOTER_MID))
    assert top.progress == 32 and top.first_line == 1 and top.at_top and not top.at_end
    end = reading_state(screen_with(["x"], FOOTER_END))
    assert end.at_end and not end.at_top
    old = reading_state(screen_with(["x"], "  瀏覽 P.2(100%)  (h)求助"))  # old status bar option
    assert old.at_end and old.first_line is None and not old.at_top
    one = reading_state(screen_with(["x"], "  瀏覽 第 1/1 頁 (100%)  目前顯示: 第 01~09 行"))
    assert one.at_top and one.at_end


def test_merged_push_rows_only_hides_repeats_of_the_same_id():
    s = screen_with([
        "推 alice: first line                          1.2.3.4 11/14 10:00",
        "→ alice: second line                           11/14 10:00",
        "→ alice  : third (padded id)                   11/14 10:01",
        "噓 bob: other person",
        "→ alice: alice again after bob is a new block",
        "→ ALICE: same id in other case, merged",
        "plain article text",
        "→ alice: after a break is not merged",
    ], FOOTER_MID)
    merged = merged_push_rows(s)
    assert set(merged) == {1, 2, 5}
    assert merged[1] == len("→ alice:") + 1                # "→" takes two cells
    assert merged[2] == len("→ alice  :") + 1
    assert s.rows - 1 not in merged


def make_term(lines, footer):
    sess = PttSession()
    term = TerminalWidget(sess)
    term.resize(800, 480)
    sess.screen.feed("\r\n".join(lines).encode("cp950"))
    if footer:
        sess.screen.feed(f"\x1b[{sess.screen.rows};1H{footer}".encode("cp950"))
    sess.screenChanged.emit()
    sent = []
    sess.send_user_bytes = lambda data: sent.append(bytes(data)) or True
    return term, sent


def wheel(term, dy):
    term.wheelEvent(QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, dy),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False))


def test_wheel_never_leaves_the_article(qapp):
    term, sent = make_term(["article"], FOOTER_MORE)
    wheel(term, -120)                                      # down inside the article: 'j' never quits
    wheel(term, 120)                                       # up: 'k'
    assert sent == [b"jj", b"kk"]
    term, sent = make_term(["article"], FOOTER_END)
    notes = []
    term.notice.connect(notes.append)
    wheel(term, -120)                                      # at 100%: nothing (KEY_DOWN would open the next post)
    assert sent == [] and notes and "結尾" in notes[0]
    wheel(term, 120)
    assert sent == [b"kk"]
    term, sent = make_term(["article"], FOOTER_MID)
    wheel(term, 120)                                       # first line: nothing (no previous post)
    assert sent == []
    term, sent = make_term(["board list"], "")
    wheel(term, -120)                                      # not reading: arrows as before
    assert sent == [b"\x1b[B\x1b[B"]


def test_left_edge_arrow_goes_back_to_the_list(qapp):
    term, sent = make_term(["article"], FOOTER_MID)
    left = QPointF(term.ox + 2, term.height() / 2)
    term.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, left, left, Qt.MouseButton.NoButton,
                                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert term._edge_hover
    img = QImage(term.size(), QImage.Format.Format_RGB32)
    term.render(img)                                       # arrow overlay paints without errors
    term.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, left, left, Qt.MouseButton.LeftButton,
                                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert sent == [b"\x1b[D"] and not term.has_selection()
    mid = QPointF(term.ox + term.cw * 10, term.height() / 2)
    term.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, mid, mid, Qt.MouseButton.NoButton,
                                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert not term._edge_hover
    term2, sent2 = make_term(["board list"], "")           # no article open: no arrow, normal selection
    term2.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, left, left, Qt.MouseButton.NoButton,
                                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert not term2._edge_hover


def test_push_merge_paints_and_can_be_turned_off(qapp):
    term, _sent = make_term(["推 alice: one", "→ alice: two"], FOOTER_MID)
    img = QImage(term.size(), QImage.Format.Format_RGB32)
    term.render(img)
    term.push_merge = False
    term.render(img)
    assert "→ alice: two" in term.s.screen.row_text(1)      # screen text (copy) is never changed
