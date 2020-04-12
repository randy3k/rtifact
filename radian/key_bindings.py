from __future__ import unicode_literals
import re
import os

from prompt_toolkit.application.current import get_app
from prompt_toolkit.application.run_in_terminal import run_in_terminal
from prompt_toolkit.eventloop import From, ensure_future
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.filters import Condition, has_focus, \
    emacs_insert_mode, vi_insert_mode, in_paste_mode, has_completions, completion_is_selected
from prompt_toolkit.filters import (
    emacs_mode,
    has_selection
)
from prompt_toolkit.enums import DEFAULT_BUFFER

from radian.settings import radian_settings as settings
from radian.document import cursor_in_string
from radian import get_app as get_radian_app
from rchitect.interface import roption


from six import text_type


default_focussed = has_focus(DEFAULT_BUFFER)
insert_mode = vi_insert_mode | emacs_insert_mode

_prompt_mode_cache = {}


def prompt_mode(mode):
    try:
        return _prompt_mode_cache[mode]
    except KeyError:
        pass
    app = get_radian_app()
    condition = Condition(lambda: app.session.current_mode_name == mode)
    _prompt_mode_cache[mode] = condition
    return condition


_preceding_text_cache = {}
_following_text_cache = {}


def preceding_text(pattern):
    try:
        return _preceding_text_cache[pattern]
    except KeyError:
        pass
    m = re.compile(pattern)

    def _preceding_text():
        app = get_app()
        return bool(m.match(app.current_buffer.document.current_line_before_cursor))

    condition = Condition(_preceding_text)
    _preceding_text_cache[pattern] = condition
    return condition


def following_text(pattern):
    try:
        return _following_text_cache[pattern]
    except KeyError:
        pass
    m = re.compile(pattern)

    def _following_text():
        app = get_app()
        return bool(m.match(app.current_buffer.document.current_line_after_cursor))

    condition = Condition(_following_text)
    _following_text_cache[pattern] = condition
    return condition


@Condition
def string_scope():
    app = get_app()
    return cursor_in_string(app.current_buffer.document)


@Condition
def cursor_at_begin():
    return get_app().current_buffer.cursor_position == 0


@Condition
def cursor_at_end():
    app = get_app()
    return app.current_buffer.cursor_position == len(app.current_buffer.text)


@Condition
def text_is_empty():
    app = get_app()
    return not app.current_buffer.text


@Condition
def auto_indentation():
    return settings.auto_indentation


@Condition
def auto_match():
    return settings.auto_match


@Condition
def has_complete_index():
    app = get_app()
    cs = app.current_buffer.complete_state
    return cs and cs.complete_index is not None


def if_no_repeat(event):
    return not event.is_repeat


def commit_text(event, text, add_history=True):
    app = get_radian_app()
    app.session.add_history = add_history
    buf = event.current_buffer
    buf.text = text
    buf.validate_and_handle()


def newline(event, chars=["{", "[", "("]):
    should_indent = event.current_buffer.document.char_before_cursor in chars
    copy_margin = not in_paste_mode() and settings.auto_indentation
    event.current_buffer.newline(copy_margin=copy_margin)
    if should_indent and settings.auto_indentation:
        tab_size = settings.tab_size
        event.current_buffer.insert_text(" " * tab_size)


def create_prompt_key_bindings(prase_text_complete):
    kb = KeyBindings()
    handle = kb.add

    @Condition
    def prase_complete():
        app = get_app()
        return prase_text_complete(app.current_buffer.text)

    @handle('c-j', filter=insert_mode & default_focussed)
    @handle('enter', filter=insert_mode & default_focussed)
    def _(event):
        newline(event)

    @handle('c-j', filter=insert_mode & default_focussed & prase_complete)
    @handle('enter', filter=insert_mode & default_focussed & prase_complete)
    def _(event):
        event.current_buffer.validate_and_handle()

    @handle('c-j', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*\{$") & following_text(r"^\}"))
    @handle('enter', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*\{$") & following_text(r"^\}"))
    def _(event):
        copy_margin = not in_paste_mode() and settings.auto_indentation
        event.current_buffer.newline(copy_margin=copy_margin)
        if settings.auto_indentation:
            tab_size = settings.tab_size
            event.current_buffer.insert_text(" " * tab_size)
        event.current_buffer.insert_text("\n")
        event.current_buffer.cursor_position -= 1

    # auto match
    @handle('(', filter=insert_mode & default_focussed & auto_match & following_text(r"[,)}\]]|$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text("()")
        event.current_buffer.cursor_left()

    @handle('[', filter=insert_mode & default_focussed & auto_match & following_text(r"[,)}\]]|$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text("[]")
        event.current_buffer.cursor_left()

    @handle('{', filter=insert_mode & default_focussed & auto_match & following_text(r"[,)}\]]|$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text("{}")
        event.current_buffer.cursor_left()

    @handle('"', filter=insert_mode & default_focussed & auto_match & following_text(r"[,)}\]]|$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text('""')
        event.current_buffer.cursor_left()

    @handle("'", filter=insert_mode & default_focussed & auto_match & following_text(r"[,)}\]]|$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text("''")
        event.current_buffer.cursor_left()

    # raw string
    @handle('(', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*(r|R)[\"'](-*)$"))
    def _(event):
        matches = re.match(r".*(r|R)[\"'](-*)", event.current_buffer.document.current_line_before_cursor)
        dashes = matches.group(2) or ""
        event.current_buffer.insert_text("()" + dashes)
        event.current_buffer.cursor_left(len(dashes) + 1)

    @handle('[', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*(r|R)[\"'](-*)$"))
    def _(event):
        matches = re.match(r".*(r|R)[\"'](-*)", event.current_buffer.document.current_line_before_cursor)
        dashes = matches.group(2) or ""
        event.current_buffer.insert_text("[]" + dashes)
        event.current_buffer.cursor_left(len(dashes) + 1)

    @handle('{', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*(r|R)[\"'](-*)$"))
    def _(event):
        matches = re.match(r".*(r|R)[\"'](-*)", event.current_buffer.document.current_line_before_cursor)
        dashes = matches.group(2) or ""
        event.current_buffer.insert_text("{}" + dashes)
        event.current_buffer.cursor_left(len(dashes) + 1)

    @handle('"', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*(r|R)$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text('""')
        event.current_buffer.cursor_left()

    @handle("'", filter=insert_mode & default_focussed & auto_match & preceding_text(r".*(r|R)$") & ~string_scope)
    def _(event):
        event.current_buffer.insert_text("''")
        event.current_buffer.cursor_left()

    # just move cursor
    @handle(')', filter=insert_mode & default_focussed & auto_match & following_text(r"^\)"))
    @handle(']', filter=insert_mode & default_focussed & auto_match & following_text(r"^\]"))
    @handle('}', filter=insert_mode & default_focussed & auto_match & following_text(r"^\}"))
    @handle('"', filter=insert_mode & default_focussed & auto_match & following_text("^\""))
    @handle("'", filter=insert_mode & default_focussed & auto_match & following_text("^'"))
    def _(event):
        event.current_buffer.cursor_right()

    @handle('backspace', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*\($") & following_text(r"^\)"))
    @handle('backspace', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*\[$") & following_text(r"^\]"))
    @handle('backspace', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*\{$") & following_text(r"^\}"))
    @handle('backspace', filter=insert_mode & default_focussed & auto_match & preceding_text('.*"$') & following_text('^"'))
    @handle('backspace', filter=insert_mode & default_focussed & auto_match & preceding_text(r".*'$") & following_text(r"^'"))
    def _(event):
        event.current_buffer.delete()
        event.current_buffer.delete_before_cursor()

    # indentation
    @handle('}', filter=insert_mode & default_focussed & auto_indentation & preceding_text(r"^\s*$"))
    @handle(']', filter=insert_mode & default_focussed & auto_indentation & preceding_text(r"^\s*$"))
    @handle(')', filter=insert_mode & default_focussed & auto_indentation & preceding_text(r"^\s*$"))
    def _(event):
        text = event.current_buffer.document.text_before_cursor
        textList = text.split("\n")
        if len(textList) >= 2:
            m = re.match(r"^\s*$", textList[-1])
            if m:
                current_indentation = m.group(0)
                previous_indentation = re.match(r"^\s*", textList[-2]).group(0)
                tab_size = settings.tab_size
                if len(current_indentation) >= settings.tab_size and \
                        current_indentation == previous_indentation:
                    event.current_buffer.delete_before_cursor(tab_size)

        event.current_buffer.insert_text(event.data)

    @handle('backspace', filter=insert_mode & default_focussed & preceding_text(r"^\s+$"))
    def _(event):
        tab_size = settings.tab_size
        buf = event.current_buffer
        leading_spaces = len(buf.document.text_before_cursor)
        buf.delete_before_cursor(min(tab_size, leading_spaces))

    @handle('tab', filter=insert_mode & default_focussed & preceding_text(r"^\s*$"))
    def _(event):
        tab_size = settings.tab_size
        event.current_buffer.insert_text(" " * tab_size)

    # bracketed paste
    @handle(Keys.BracketedPaste, filter=default_focussed)
    def _(event):
        data = event.data

        data = data.replace('\r\n', '\n')
        data = data.replace('\r', '\n')

        should_eval = data and data[-1] == "\n" and \
            len(event.current_buffer.document.text_after_cursor) == 0
        # todo: allow partial prase complete
        if should_eval and prase_text_complete(data):
            data = data.rstrip("\n")
            event.current_buffer.insert_text(data)
            event.current_buffer.validate_and_handle()
        else:
            event.current_buffer.insert_text(data)

    return kb


# keybinds for both r mond and browse mode
def create_r_key_bindings(prase_text_complete):
    kb = create_prompt_key_bindings(prase_text_complete)
    handle = kb.add

    # r mode
    @handle(';', filter=insert_mode & default_focussed & cursor_at_begin)
    def _(event):
        app = get_radian_app()
        app.session.change_mode("shell")

    return kb


def create_shell_key_bindings():
    kb = KeyBindings()
    handle = kb.add

    # shell mode
    @handle(
        'backspace',
        filter=insert_mode & default_focussed & cursor_at_begin,
        save_before=if_no_repeat)
    def _(event):
        app = get_radian_app()
        app.session.change_mode("r")

    @handle('c-j', filter=insert_mode & default_focussed)
    @handle('enter', filter=insert_mode & default_focussed)
    def _(event):
        event.current_buffer.validate_and_handle()

    return kb


def create_key_bindings(editor=""):
    kb = KeyBindings()
    handle = kb.add

    # emit completion
    @handle('c-j', filter=insert_mode & default_focussed & completion_is_selected)
    @handle('enter', filter=insert_mode & default_focussed & completion_is_selected)
    def _(event):
        event.current_buffer.complete_state = None

    # cancel completion
    @handle('c-c', filter=default_focussed & has_completions)
    def _(event):
        event.current_buffer.cancel_completion()

    # new line
    @handle('escape', 'enter', filter=emacs_insert_mode)
    def _(event):
        if event.current_buffer.text:
            copy_margin = not in_paste_mode() and settings.auto_indentation
            event.current_buffer.newline(copy_margin=copy_margin)

    @handle('c-x', 'c-e', filter=emacs_mode & ~has_selection)
    def _(event):
        # match R behavior
        editor = roption("editor")
        if not editor or not isinstance(editor, text_type):
            if 'VISUAL' in os.environ:
                editor = os.environ['VISUAL']
            elif 'EDITOR' in os.environ:
                editor = os.environ['EDITOR']
            if not editor:
                editor = "vi"

        buff = event.current_buffer
        if editor:
            orig_visual = os.environ['VISUAL'] if 'VISUAL' in os.environ else None
            os.environ['VISUAL'] = editor

        buff.open_in_editor()

        if editor:
            def run():
                def cleanup():
                    if orig_visual:
                        os.environ['VISUAL'] = orig_visual
                    else:
                        del os.environ['VISUAL']

                yield From(run_in_terminal(cleanup, in_executor=True))

            ensure_future(run())

    return kb


def map_key(key, value, mode="r", filter_str=""):
    app = get_radian_app()
    kb = app.session.modes[mode].prompt_key_bindings
    @kb.add(*key, filter=insert_mode & default_focussed, eager=True)
    def _(event):
        event.current_buffer.insert_text(value)
