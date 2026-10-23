from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from src.net.session import PttSession
from src.ui.terminal_widget import TerminalWidget


def make_term(*lines: str) -> TerminalWidget:
    term = TerminalWidget(PttSession())
    term.resize(720, 480)
    term.s.screen.feed(("\r\n".join(lines)).encode("cp950"))
    term._refresh_links()
    term.show()
    QApplication.processEvents()
    return term


def point_for(term: TerminalWidget, col: int, row: int) -> QPointF:
    return QPointF(term.ox + (col + 0.5) * term.cw, term.oy + (row + 0.5) * term.ch)


def mouse_event(kind, pos, button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.NoButton, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(kind, pos, pos, button, buttons, mods)


def drag(term: TerminalWidget, start, end, mods=Qt.KeyboardModifier.NoModifier):
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))
    term.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, mods))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods))


def test_drag_selects_text_and_sends_no_bytes(qapp, monkeypatch):
    term = make_term("hello world")
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(data) or True)
    drag(term, point_for(term, 0, 0), point_for(term, 4, 0))
    assert term.has_selection()
    assert term.selection_text() == "hello"
    assert sent == []


def test_drag_across_rows_selects_middle_rows_whole(qapp):
    term = make_term("abc   ", "def", "ghi   ")
    drag(term, point_for(term, 1, 0), point_for(term, 1, 2))
    assert term.selection_text() == "bc\ndef\ngh"


def test_drag_starting_on_link_selects_and_does_not_open(qapp):
    term = make_term("?? https://example.com/a")
    link = term.links()[0]
    activated = []
    term.linkActivated.connect(activated.append)
    start = point_for(term, link.start_col + 1, link.row)
    end = QPointF(start.x() + 14, start.y())
    drag(term, start, end)
    assert activated == []
    assert term.has_selection()


def test_wide_character_is_never_split_by_drag(qapp):
    term = make_term("???")
    drag(term, point_for(term, 1, 0), QPointF(point_for(term, 2, 0).x() + 6, point_for(term, 2, 0).y()))
    assert term.selection_text() == "??"


def test_alt_drag_selects_a_rectangle(qapp):
    term = make_term("abcdef   ", "ghijkl   ", "mnopqr   ")
    drag(term, point_for(term, 1, 0), point_for(term, 3, 2), Qt.KeyboardModifier.AltModifier)
    assert term.selection_text() == "bcd\nhij\nnop"


def test_single_click_on_blank_area_clears_selection(qapp):
    term = make_term("hello world")
    drag(term, point_for(term, 0, 0), point_for(term, 4, 0))
    pos = point_for(term, 40, 5)
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    assert not term.has_selection()


def test_screen_update_clears_selection(qapp):
    term = make_term("hello world")
    drag(term, point_for(term, 0, 0), point_for(term, 4, 0))
    term.s.screenChanged.emit()
    assert not term.has_selection()


def test_user_key_that_is_sent_clears_selection(qapp, monkeypatch):
    term = make_term("hello world")
    drag(term, point_for(term, 0, 0), point_for(term, 4, 0))
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(data) or True)
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_C, Qt.KeyboardModifier.ControlModifier))
    assert sent == [b"\x03"]
    assert not term.has_selection()


def test_double_click_selects_word_and_triple_click_selects_line(qapp):
    term = make_term("hello ?? world")
    pos = point_for(term, 7, 0)
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    term.mouseDoubleClickEvent(mouse_event(QEvent.Type.MouseButtonDblClick, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    assert term.selection_text() == "??"
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    assert term.selection_text() == "hello ?? world"


def test_selected_cells_are_painted_differently(qapp):
    term = make_term("AAAA")
    plain = term.grab().toImage()
    term._sel_anchor, term._sel_cursor = (0, 0), (0, 3)
    term._sel_rect = False
    term.update()
    picked = term.grab().toImage()
    assert plain != picked


def test_ctrl_shift_c_copies_selection_without_sending_bytes(qapp, monkeypatch):
    term = make_term("hello world")
    drag(term, point_for(term, 0, 0), point_for(term, 4, 0))
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(data) or True)
    QGuiApplication.clipboard().setText("old")
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_C,
                                 Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
    assert QGuiApplication.clipboard().text() == "hello"
    assert sent == []
    assert term.has_selection()


def test_copy_without_selection_does_nothing(qapp):
    term = make_term("hello")
    QGuiApplication.clipboard().setText("keep")
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_C,
                                 Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
    assert QGuiApplication.clipboard().text() == "keep"


def test_copy_selection_strips_line_ends_and_joins_with_newline(qapp):
    term = make_term("abc   ", "def", "ghi   ")
    drag(term, point_for(term, 1, 0), point_for(term, 1, 2))
    assert term.copy_selection()
    assert QGuiApplication.clipboard().text() == "bc\ndef\ngh"


def test_select_all_and_copy_whole_screen(qapp):
    term = make_term("hello", "world")
    term.select_all()
    assert term.has_selection()
    assert term.selection_text() == "hello\nworld"
    assert term.copy_screen()
    assert QGuiApplication.clipboard().text() == "hello\nworld"
    assert term.copy_selection()
    assert QGuiApplication.clipboard().text() == "hello\nworld"


def test_context_menu_offers_copy_select_all_and_copy_screen(qapp):
    term = make_term("hello", "world")
    menu = term._build_context_menu()
    actions = {a.text(): a for a in menu.actions()}
    assert {"\u8907\u88fd", "\u5168\u9078\u756b\u9762", "\u8907\u88fd\u6574\u500b\u756b\u9762"} <= set(actions)
    assert not actions["\u8907\u88fd"].isEnabled()
    actions["\u5168\u9078\u756b\u9762"].trigger()
    assert term.has_selection()
    menu2 = term._build_context_menu()
    actions2 = {a.text(): a for a in menu2.actions()}
    assert actions2["\u8907\u88fd"].isEnabled()
    actions2["\u8907\u88fd"].trigger()
    assert QGuiApplication.clipboard().text() == "hello\nworld"
    menu3 = term._build_context_menu()
    {a.text(): a for a in menu3.actions()}["\u8907\u88fd\u6574\u500b\u756b\u9762"].trigger()
    assert QGuiApplication.clipboard().text() == "hello\nworld"
