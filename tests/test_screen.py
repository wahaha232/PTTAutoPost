from src.terminal.detect import Kind, classify, editor_is_empty, title_prompt_is_empty
from src.terminal.screen import BOLD, WIDE2, Screen


def feed_text(s, text, enc="cp950"):
    s.feed(text.encode(enc))


def test_plain_text_and_crlf():
    s = Screen()
    s.feed(b"hello\r\nworld")
    assert s.row_text(0) == "hello" and s.row_text(1) == "world"


def test_big5_double_width_cells():
    s = Screen()
    feed_text(s, "批踢踢ab")
    assert s.row_text(0) == "批踢踢ab"
    assert s.grid[0][0][0] == "批" and s.grid[0][1][3] & WIDE2
    assert s.cur.x == 8  # 3 wide chars (6 cells) + 2


def test_symbols_decoded_from_two_bytes_take_two_cells():
    s = Screen()
    s.feed("◢█".encode("cp950") + b"x")
    assert s.cur.x == 5


def test_big5_char_split_across_chunks():
    s = Screen()
    raw = "中文".encode("cp950")
    s.feed(raw[:1])
    s.feed(raw[1:3])
    s.feed(raw[3:])
    assert s.row_text(0) == "中文"


def test_colour_escape_between_the_two_bytes_of_a_big5_char():
    """PTT sends lead, ESC[..m, trail for coloured block art; the char must still be decoded as ONE wide char."""
    s = Screen()
    s.feed(b"\xa2\x1b[31mb")                       # A2 62 = U+2581 LOWER ONE EIGHTH BLOCK
    assert s.row_text(0) == "\u2581" and s.cur.x == 2
    assert s.fg == 1                               # the escape was applied, not swallowed
    s2 = Screen()
    s2.feed(b"\xa2")
    s2.feed(b"\x1b[1;33m")                         # also when the stream is cut right after the lead byte
    s2.feed(b"c")
    assert s2.row_text(0) == "\u2582" and s2.fg == 3


def test_dangling_lead_byte_before_a_line_break_is_not_swallowed():
    s = Screen()
    s.feed(b"\xa4\r\nok")
    assert s.row_text(0) == "\uff1f" and s.row_text(1) == "ok"


def test_real_login_screen_art_has_no_placeholders():
    """Regression: a captured real PTT login frame (lead byte, colour escape, trail byte) decodes without '？'."""
    frame = (b"\x1b[2J\x1b[H     \x1b[;30m\xa2\x1b[31mb\xa2\x1b[1;37mi\xa2\x1b[mc  "
             + "請輸入代號：".encode("cp950"))
    s = Screen()
    s.feed(frame)
    assert s.row_text(0).startswith("     ▁█▂") and "？" not in s.row_text(0)


def test_cursor_positioning_and_erase():
    s = Screen()
    s.feed(b"\x1b[2J\x1b[5;10Habc\x1b[1;1HZ\x1b[24;1Hlast")
    assert s.row_text(4).strip() == "abc" and s.grid[4][9][0] == "a"
    assert s.row_text(0) == "Z"
    assert s.row_text(23) == "last"
    s.feed(b"\x1b[5;11H\x1b[K")  # erase from cursor
    assert s.row_text(4) == " " * 9 + "a"


def test_erase_uses_current_background():
    s = Screen()
    s.feed(b"\x1b[44m\x1b[K")
    assert s.grid[0][79][2] == 4


def test_ris_clears_the_screen_but_keeps_session_statistics():
    s = Screen()
    s.feed(b"hello\x07\x1bc")
    assert s.bytes_fed == 8 and s.bell == 1                          # ESC c must not re-run __init__
    assert s.text().strip() == "" and s.cur.x == 0 and s.cur.y == 0


def test_sgr_colors_and_reset():
    s = Screen()
    s.feed(b"\x1b[1;31;42mA\x1b[0mB")
    assert s.grid[0][0][1:3] == (1, 2) and s.grid[0][0][3] & BOLD
    assert s.grid[0][1][1:3] == (7, 0) and not s.grid[0][1][3]


def test_deferred_wrap_does_not_skip_a_row():
    s = Screen()
    s.feed(b"x" * 80 + b"\r\nnext")
    assert s.row_text(0) == "x" * 80 and s.row_text(1) == "next"


def test_scroll_at_bottom():
    s = Screen()
    for i in range(30):
        s.feed(f"line{i}\r\n".encode())
    assert s.row_text(0).startswith("line") and "line29" in s.text()
    assert s.row_text(0) != "line0"


def test_backspace_and_overwrite():
    s = Screen()
    s.feed(b"ab\x08c")
    assert s.row_text(0) == "ac"


def test_classify_login_flow_screens():
    s = Screen()
    feed_text(s, "請輸入代號，或以 guest 參觀，或以 new 註冊: ")
    assert classify(s) == Kind.LOGIN_PROMPT
    s = Screen()
    feed_text(s, "請輸入您的密碼:")
    assert classify(s) == Kind.PASSWORD_PROMPT
    s = Screen()
    feed_text(s, "密碼不對或無此帳號。程式結束")
    assert classify(s) == Kind.CRED_FAILURE
    s = Screen()
    feed_text(s, "您想刪除其他重複登入的連線嗎？[Y/n]")
    assert classify(s) == Kind.DUP_LOGIN
    s = Screen()
    feed_text(s, "【主功能表】 批踢踢實業坊")
    assert classify(s) == Kind.MAIN_MENU
    assert classify(Screen()) == Kind.UNKNOWN


def test_classify_post_screens():
    s = Screen()
    feed_text(s, "標題：")
    assert classify(s) == Kind.TITLE_PROMPT and title_prompt_is_empty(s)
    feed_text(s, "abc")
    assert not title_prompt_is_empty(s)
    e = Screen()
    e.feed(b"\x1b[24;1H")
    feed_text(e, " 編輯文章  (^Z/F1)說明 (^P/^G)插入符號/範本 (^X/^Q)離開")
    e.feed(b"\x1b[1;1H")
    assert classify(e) == Kind.EDITOR and editor_is_empty(e)
    e.feed(b"\x1b[1;1Hhi")
    assert not editor_is_empty(e)


def test_telnet_iac_sequences_are_stripped():
    from src.net.telnet import IacFilter
    f = IacFilter()
    raw = b"\xff\xfd\x18\xff\xfb\x01hello\xff\xfa\x18\x01\xff\xf0 world\xff\xff!"
    out = f.feed(raw[:5]) + f.feed(raw[5:11]) + f.feed(raw[11:])      # split across chunks
    assert out == b"hello world\xff!" and f.stripped == 3


def test_extended_colour_sgr_is_skipped_not_misread_as_blink():
    from src.terminal.screen import BLINK
    s = Screen()
    s.feed(b"\x1b[38;5;196mA\x1b[48;2;1;2;3mB\x1b[0mC")
    assert [s.grid[0][i][0] for i in range(3)] == ["A", "B", "C"]
    assert not any(s.grid[0][i][3] & BLINK for i in range(3))


def test_huge_csi_counts_and_long_sequences_do_not_stall_or_grow():
    import time
    s = Screen()
    t0 = time.perf_counter()
    s.feed(b"\x1b[999999L\x1b[999999M\x1b[999999A\x1b[999999B")
    assert time.perf_counter() - t0 < 0.5 and len(s.grid) == s.rows
    s.feed(b"\x1b[" + b"1;" * 100000 + b"mX")
    assert len(s._csi) <= 64
    s.feed(b"\x1b[0mhello")
    assert "hello" in s.row_text(s.cur.y)


def _wide_ok(s, y=0):
    """Every WIDE2 cell follows a non-WIDE2 lead with text; no orphan halves."""
    row = s.grid[y]
    for x, cell in enumerate(row):
        if cell[3] & WIDE2:
            assert x > 0 and not row[x - 1][3] & WIDE2 and row[x - 1][0].strip(), (x, row[x - 1:x + 1])
    return True


def test_delete_insert_erase_never_leave_orphan_wide_halves():
    for seq, expect in ((b"\x1b[1;2H\x1b[P", "a d"),       # ESC[P deletes the lead of 中: its trail is blanked
                        (b"\x1b[1;3H\x1b[P", "a d"),       # ESC[P deletes only the trail: the lead is blanked
                        (b"\x1b[1;3H\x1b[@", "a   d"),     # insert between the halves: both blanked
                        (b"\x1b[1;3H\x1b[X", "a  d"),     # erase the trail only
                        (b"\x1b[1;3H\x1b[K", "a"),         # erase to end from the trail
                        (b"\x1b[1;2H\x1b[1K", "   d")):   # erase to start through the lead
        s = Screen()
        feed_text(s, "a中d")
        s.feed(seq)
        assert _wide_ok(s) and s.row_text(0) == expect, seq


def test_insert_pushing_a_lead_to_the_right_edge_blanks_it():
    s = Screen(cols=6)
    feed_text(s, "abcd中")
    s.feed(b"\x1b[1;1H\x1b[@")
    assert _wide_ok(s) and s.row_text(0) == " abcd"
