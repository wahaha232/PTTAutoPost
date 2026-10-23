from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from src.net.session import PttSession
from src.ui.terminal_widget import TerminalWidget


def make_term(text: str = "中文 https://example.com/a") -> TerminalWidget:
    term = TerminalWidget(PttSession())
    term.resize(720, 480)
    term.s.screen.feed(text.encode("cp950"))
    term._refresh_links()
    term.show()
    QApplication.processEvents()
    return term


def point_for(term: TerminalWidget, col: int, row: int) -> QPointF:
    return QPointF(term.ox + (col + 0.5) * term.cw, term.oy + (row + 0.5) * term.ch)


def mouse_event(kind, pos, button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.NoButton):
    return QMouseEvent(kind, pos, pos, button, buttons, Qt.KeyboardModifier.NoModifier)


def test_hover_underlines_link_and_changes_cursor(qapp):
    term = make_term()
    link = term.links()[0]
    term.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, point_for(term, link.start_col + 1, link.row)))
    assert term._hover_link == link
    assert term.cursor().shape() == Qt.CursorShape.PointingHandCursor
    term.leaveEvent(QEvent(QEvent.Type.Leave))
    assert term._hover_link is None
    assert term.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_detected_links_are_underlined_without_hover(qapp):
    term = make_term()
    assert term.links()
    with_link = term.grab().toImage()
    term._links = []
    term._hover_link = None
    term.update()
    without_link = term.grab().toImage()
    assert with_link != without_link


def test_click_opens_once_and_does_not_send_terminal_bytes(qapp, monkeypatch):
    term = make_term()
    link = term.links()[0]
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(data) or True)
    activated = []
    term.linkActivated.connect(activated.append)
    pos = point_for(term, link.start_col + 1, link.row)
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    assert activated == [link.url]
    assert sent == []


def test_drag_does_not_open_link(qapp):
    term = make_term()
    link = term.links()[0]
    activated = []
    term.linkActivated.connect(activated.append)
    start = point_for(term, link.start_col + 1, link.row)
    end = QPointF(start.x() + QApplication.startDragDistance() + 20, start.y())
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton))
    assert activated == []


def test_click_on_plain_text_does_not_open(qapp):
    term = make_term()
    activated = []
    term.linkActivated.connect(activated.append)
    pos = point_for(term, 0, 0)
    term.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    term.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton))
    assert activated == []
