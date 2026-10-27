from src.terminal.screen import Screen
from src.terminal.selection import clamp, screen_text, selection_rows, selection_text, word_span


def screen(*lines: str) -> Screen:
    s = Screen()
    s.feed(("\r\n".join(lines)).encode("cp950"))
    return s


def test_linear_same_row_and_trailing_spaces():
    s = screen("hello world   ")
    assert selection_text(s.grid, (0, 0), (0, 4)) == "hello"
    assert selection_text(s.grid, (0, 4), (0, 0)) == "hello"
    assert selection_text(s.grid, (0, 6), (0, 10)) == "world"


def test_linear_multiline_whole_middle_rows():
    s = screen("abc   ", "def", "ghi   ")
    rows = selection_rows(s.grid, (0, 1), (2, 1))
    assert rows == [(0, 1, 79), (1, 0, 79), (2, 0, 1)]
    assert selection_text(s.grid, (0, 1), (2, 1)) == "bc\ndef\ngh"


def test_linear_multiline_reversed_anchor():
    s = screen("abc   ", "def", "ghi   ")
    assert selection_text(s.grid, (2, 1), (0, 1)) == selection_text(s.grid, (0, 1), (2, 1))


def test_wide_character_cannot_be_split():
    s = screen("中文測")
    assert selection_rows(s.grid, (0, 1), (0, 1)) == [(0, 0, 1)]
    assert selection_text(s.grid, (0, 1), (0, 1)) == "中"
    assert selection_rows(s.grid, (0, 2), (0, 2)) == [(0, 2, 3)]
    assert selection_text(s.grid, (0, 2), (0, 2)) == "文"
    assert selection_text(s.grid, (0, 3), (0, 4)) == "文測"
    assert selection_rows(s.grid, (0, 3), (0, 4)) == [(0, 2, 5)]


def test_rectangular_selection():
    s = screen("abc   ", "def   ", "ghi   ", "jkl   ")
    rows = selection_rows(s.grid, (0, 0), (2, 1), rect=True)
    assert rows == [(0, 0, 1), (1, 0, 1), (2, 0, 1)]
    assert selection_text(s.grid, (0, 0), (2, 1), rect=True) == "ab\nde\ngh"
    assert selection_text(s.grid, (2, 1), (0, 0), rect=True) == "ab\nde\ngh"


def test_rectangular_selection_expands_wide_cells():
    s = screen("中文測")
    assert selection_text(s.grid, (0, 2), (0, 2), rect=True) == "文"
    assert selection_rows(s.grid, (0, 3), (0, 3), rect=True) == [(0, 2, 3)]


def test_word_span_around_ascii_and_chinese():
    s = screen("hello 中文 world")
    assert word_span(s.grid, 0, 1) == (0, 4)
    assert word_span(s.grid, 0, 7) == (6, 9)
    assert word_span(s.grid, 0, 12) == (11, 15)
    assert word_span(s.grid, 0, 5) is None
    assert word_span(s.grid, 0, 40) is None


def test_whole_line_selection_uses_full_row():
    s = screen("hello 中文 world")
    assert selection_text(s.grid, (0, 0), (0, 79)) == "hello 中文 world"


def test_screen_text_strips_rows_and_trailing_blank_rows():
    s = screen("a  ", "b   ", "")
    assert screen_text(s.grid) == "a\nb"


def test_clamp_keeps_points_on_the_grid():
    assert clamp((-3, 999), 80, 24) == (0, 79)
    assert clamp((99, -1), 80, 24) == (23, 0)


def test_word_span_does_not_wrap_to_the_last_column_on_an_orphan_trail():
    from src.terminal.screen import WIDE2
    grid = [[("", 7, 0, WIDE2), ("a", 7, 0, 0), ("b", 7, 0, 0), (" ", 7, 0, 0), ("z", 7, 0, 0)]]
    assert word_span(grid, 0, 1) == (1, 2)
