from __future__ import unicode_literals
import sys
from helpers import assert_equal, assert_startswith, screen_process


def test_startup():

    with screen_process([sys.executable, "-m", "rtichoke"]) as screen:
        assert_startswith(lambda: screen.display[0], "R ")
        assert_equal(lambda: (screen.cursor.x, screen.cursor.y), (4, 3))
        assert_startswith(lambda: screen.display[3], "r$>")
