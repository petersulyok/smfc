#
#   app.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.app: the curses loop of smfc-config.
#
import curses
import sys
from typing import List, Optional

from smfc.config_editor import panes
from smfc.config_editor.model import EditorModel, FieldState, FieldView, Row
from smfc.config_editor.panes import Layout
from smfc.config_editor.schema import Widget

# The colour scheme, taken from the Debian installer: a painted banner and key bar, light panes and a
# strong selection bar. Colour carries orientation here. The glyphs say the same thing without it, so
# a monochrome terminal and --no-color lose nothing but the orientation.
COLOURS: tuple = (
    (panes.PAIR_BANNER, curses.COLOR_WHITE, curses.COLOR_BLUE),
    (panes.PAIR_PANE, curses.COLOR_BLACK, curses.COLOR_WHITE),
    (panes.PAIR_SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE),
    (panes.PAIR_TITLE, curses.COLOR_BLUE, curses.COLOR_WHITE),
    (panes.PAIR_KEYS, curses.COLOR_BLACK, curses.COLOR_CYAN),
    (panes.PAIR_OK, curses.COLOR_GREEN, curses.COLOR_WHITE),
    (panes.PAIR_WARN, curses.COLOR_YELLOW, curses.COLOR_WHITE),
    (panes.PAIR_ERROR, curses.COLOR_RED, curses.COLOR_WHITE),
    (panes.PAIR_DIM, curses.COLOR_BLUE, curses.COLOR_WHITE),
    (panes.PAIR_POPUP, curses.COLOR_BLACK, curses.COLOR_CYAN),
)

# Which pane the cursor is in.
PANE_SECTIONS: int = 0
PANE_FIELDS: int = 1


class EditorApp:
    """The screen and the keys of smfc-config.

    Everything it knows lives in `EditorModel`, and everything it draws comes from `panes`, so this
    class holds only the cursor, the scroll offsets and the key dispatch.
    """

    model: EditorModel              # The configuration file being edited
    pane: int                       # Which pane the cursor is in
    row_index: int                  # Selected row of the section list
    row_top: int                    # First row shown in the section list
    field_index: int                # Selected parameter of the right pane
    field_top: int                  # First parameter shown in the right pane
    editing: Optional[str]          # The text being typed, None when not editing
    message: str                    # One line of feedback, shown until the next key
    running: bool                   # False once the user has quit
    colour: bool                    # True when the terminal paints the scheme

    def __init__(self, model: EditorModel, colour: bool = True) -> None:
        """Build the screen state of one configuration file.
        Args:
            model (EditorModel): the configuration file to edit
            colour (bool): False to draw without colour
        """
        self.model = model
        self.colour = colour
        self.pane = PANE_SECTIONS
        self.row_index = 0
        self.row_top = 0
        self.field_index = 0
        self.field_top = 0
        self.editing = None
        self.message = ""
        self.running = True

    # -- state -------------------------------------------------------------------------------------

    @property
    def row(self) -> Row:
        """The selected row of the section list.
        Returns:
            Row: the row under the cursor
        """
        return self.model.rows[self.row_index]

    def views(self) -> List[FieldView]:
        """The parameters of the selected section.
        Returns:
            List[FieldView]: the parameters, empty for the separator and the Overview row
        """
        return self.model.fields_of(self.row)

    def view(self) -> Optional[FieldView]:
        """The selected parameter.
        Returns:
            Optional[FieldView]: the parameter under the cursor, or None when the cursor is on the left
        """
        views = self.views()
        if self.pane is PANE_SECTIONS or not views:
            return None
        return views[min(self.field_index, len(views) - 1)]

    def move_row(self, step: int) -> None:
        """Move the cursor in the section list, skipping the separator line.
        Args:
            step (int): -1 for up, 1 for down
        """
        index = self.row_index
        while True:
            index += step
            if index < 0 or index >= len(self.model.rows):
                return
            if self.model.rows[index].selectable:
                break
        self.row_index = index
        self.field_index = 0
        self.field_top = 0

    def move_field(self, step: int) -> None:
        """Move the cursor in the parameter list.
        Args:
            step (int): -1 for up, 1 for down
        """
        views = self.views()
        if not views:
            return
        self.field_index = max(0, min(self.field_index + step, len(views) - 1))

    def scroll(self, layout: Layout) -> None:
        """Keep the cursor of both panes inside the visible rows.
        Args:
            layout (Layout): the sizes the screen is drawn with
        """
        self.row_top = _clamp_top(self.row_top, self.row_index, layout.pane_rows, len(self.model.rows))
        self.field_top = _clamp_top(self.field_top, self.field_index, layout.pane_rows,
                                    len(self.views()))

    # -- actions -----------------------------------------------------------------------------------

    def start_edit(self) -> None:
        """Open the selected parameter for editing, where the editor can edit it in place."""
        view = self.view()
        if view is None:
            return
        if self.model.read_only:
            self.message = "read-only: re-run as sudo smfc-config"
            return
        if view.field is None:
            self.message = "smfc does not know this parameter; it is kept as it is"
            return
        if view.field.widget is not Widget.INLINE:
            self.message = f"{view.key} is edited in a popup, which arrives with phase 6"
            return
        self.editing = view.value

    def finish_edit(self, accept: bool) -> None:
        """Close the editor of one parameter.
        Args:
            accept (bool): True to write the typed value, False to drop it
        """
        view = self.view()
        if accept and view is not None and self.editing is not None:
            self.model.set_value(self.row, view.key, self.editing.strip())
            self.message = f"{view.key} = {self.editing.strip()}"
        self.editing = None

    def toggle(self) -> None:
        """Switch the selected family on or off."""
        if self.model.read_only:
            self.message = "read-only: re-run as sudo smfc-config"
            return
        if self.model.toggle(self.row):
            self.message = f"[{self.row.name}] {'enabled' if self.row.enabled else 'disabled'}"
        else:
            self.message = f"[{self.row.name}] is always active"

    def save(self) -> None:
        """Write the file and report what it is worth.
        Nothing blocks the save. A user has to be able to keep partial work and come back to it, so an
        error is reported rather than enforced.
        """
        try:
            self.model.save()
        except PermissionError:
            self.message = f"cannot write {self.model.path}; re-run as sudo smfc-config"
            return
        if self.model.has_errors():
            self.message = ("saved; smfc will not start with this file, and the running service keeps "
                            "its current settings")
        else:
            self.message = "saved"

    def check(self) -> None:
        """Run the checks of the whole file."""
        self.model.run_checks()
        self.message = "checked" if not self.model.has_errors() else "checked: errors found"

    # -- keys --------------------------------------------------------------------------------------

    def handle_key(self, key: int) -> None:
        """Act on one key press.
        Args:
            key (int): the key, as curses reports it
        """
        if self.editing is not None:
            self._handle_edit_key(key)
            return
        self.message = ""
        # Esc does not quit: it is the first byte of every function key sequence, and a terminal that
        # delivers them one byte at a time would otherwise close the editor on F2.
        if key in (curses.KEY_F10, ord("q")):
            self.running = False
        elif key == 27:
            self.pane = PANE_SECTIONS
        elif key == ord("\t"):
            self.pane = PANE_FIELDS if self.pane is PANE_SECTIONS else PANE_SECTIONS
        elif key in (curses.KEY_UP, ord("k")):
            self._move(-1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self._move(1)
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.pane is PANE_SECTIONS:
                self.pane = PANE_FIELDS
            else:
                self.start_edit()
        elif key == ord(" "):
            self.toggle()
        elif key == curses.KEY_F5:
            self.check()
        elif key == curses.KEY_F2:
            self.save()

    def _move(self, step: int) -> None:
        """Move the cursor of whichever pane it is in.
        Args:
            step (int): -1 for up, 1 for down
        """
        if self.pane is PANE_SECTIONS:
            self.move_row(step)
        else:
            self.move_field(step)

    def _handle_edit_key(self, key: int) -> None:
        """Act on one key press while a value is open for editing.
        Args:
            key (int): the key, as curses reports it
        """
        if key in (curses.KEY_ENTER, 10, 13):
            self.finish_edit(True)
        elif key == 27:
            self.finish_edit(False)
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.editing = (self.editing or "")[:-1]
        elif 32 <= key < 127:
            self.editing = (self.editing or "") + chr(key)

    # -- drawing -----------------------------------------------------------------------------------

    def attr(self, pair: int, bold: bool = False) -> int:
        """Build the attribute of one colour role.
        Without colour the selection falls back to reverse video, so the cursor is still visible.
        Args:
            pair (int): the colour pair number
            bold (bool): True to add bold
        Returns:
            int: the curses attribute
        """
        if not self.colour:
            base = curses.A_REVERSE if pair in (panes.PAIR_SELECT, panes.PAIR_BANNER,
                                                panes.PAIR_KEYS) else curses.A_NORMAL
            return base | (curses.A_BOLD if bold else 0)
        return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)

    def draw(self, screen: "curses.window") -> None:
        """Draw the whole screen.
        Args:
            screen (curses.window): the curses screen
        """
        height, width = screen.getmaxyx()
        layout = panes.layout_for(width, height)
        self.scroll(layout)
        screen.erase()
        screen.bkgd(" ", self.attr(panes.PAIR_PANE))
        views = self.views()
        self._draw_banner(screen, layout)
        self._draw_panes(screen, layout, views)
        self._draw_footer(screen, layout)
        screen.noutrefresh()
        curses.doupdate()

    def _draw_banner(self, screen: "curses.window", layout: Layout) -> None:
        """Draw the title line, which names the program and the file being edited.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
        """
        self._put(screen, 0, 0, " smfc-config".ljust(layout.width), layout.width,
                  self.attr(panes.PAIR_BANNER, bold=True))
        path = f"{self.model.path} "
        self._put(screen, 0, max(layout.width - len(path), 0), path, len(path),
                  self.attr(panes.PAIR_BANNER))

    def _draw_panes(self, screen: "curses.window", layout: Layout, views: List[FieldView]) -> None:
        """Draw the frame, the section list, the parameter list and the help pane.
        The whole thing is one box. The rule between the panes and the help carries the Help title, so
        the two boxes share one line instead of standing on two.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
            views (List[FieldView]): the parameters of the selected section
        """
        rule = layout.pane_rows + 1
        box = screen.derwin(rule + layout.help_rows + 2, layout.width, 1, 0)
        box.bkgd(" ", self.attr(panes.PAIR_PANE))
        box.box()
        box.hline(rule, 1, curses.ACS_HLINE, layout.width - 2)
        box.addch(rule, 0, curses.ACS_LTEE)
        box.addch(rule, layout.width - 1, curses.ACS_RTEE)
        self._put(box, rule, 2, " Help ", 6, self.attr(panes.PAIR_TITLE, bold=True))

        left = panes.render_sections(self.model, self.row_index, self.row_top, layout)
        right = panes.render_fields(views, self.field_index, self.field_top, layout, self.editing)
        if layout.two_pane:
            divider = layout.left_width + 1
            box.vline(1, divider, curses.ACS_VLINE, layout.pane_rows)
            box.addch(0, divider, curses.ACS_TTEE)
            box.addch(rule, divider, curses.ACS_BTEE)
            self._put(box, 0, 2, " Sections ", 10, self.attr(panes.PAIR_TITLE, bold=True))
            title = f" [{self.row.name}] "
            self._put(box, 0, divider + 2, title, len(title), self.attr(panes.PAIR_TITLE, bold=True))
            self._draw_section_lines(box, layout, left, 1)
            self._draw_field_lines(box, layout, right, divider + 1)
        else:
            title = " Sections " if self.pane is PANE_SECTIONS else f" [{self.row.name}] "
            self._put(box, 0, 2, title, len(title), self.attr(panes.PAIR_TITLE, bold=True))
            if self.pane is PANE_SECTIONS:
                self._draw_section_lines(box, layout, left, 1)
            else:
                self._draw_field_lines(box, layout, right, 1)

        view = self.view() if views else None
        for index, text in enumerate(panes.render_help(self.model, self.row, view, layout)):
            error = text.startswith(("error", "warn"))
            attr = self.attr(panes.PAIR_ERROR if error else panes.PAIR_PANE, bold=index == 0)
            self._put(box, rule + 1 + index, 2, text, layout.width - 4, attr)

    def _draw_section_lines(self, box: "curses.window", layout: Layout, lines: List[str],
                            column: int) -> None:
        """Draw the section list, with the two glyph columns in their own colour.
        Args:
            box (curses.window): the framed window
            layout (Layout): the sizes to draw with
            lines (List[str]): the rendered lines
            column (int): the column the pane starts at
        """
        enabled_col, check_col = panes.glyph_columns(layout)
        for index, text in enumerate(lines):
            row_index = index + self.row_top
            row = self.model.rows[row_index]
            selected = self.pane is PANE_SECTIONS and row_index == self.row_index
            base = self.attr(panes.PAIR_SELECT, bold=True) if selected else self.attr(panes.PAIR_PANE)
            self._put(box, index + 1, column, text.ljust(layout.left_width), layout.left_width, base)
            if selected:
                continue
            glyph = panes.enabled_glyph(row)
            if glyph.strip():
                self._put(box, index + 1, column + enabled_col, glyph, 1,
                          self.attr(panes.PAIR_OK if row.enabled else panes.PAIR_DIM))
            check = panes.check_glyph(self.model, row)
            if check.strip():
                pair = panes.PAIR_ERROR if check == panes.GLYPH_ERROR else (
                    panes.PAIR_WARN if check == panes.GLYPH_WARN else panes.PAIR_DIM)
                self._put(box, index + 1, column + check_col, check, 1, self.attr(pair))

    def _draw_field_lines(self, box: "curses.window", layout: Layout, lines: List[str],
                          column: int) -> None:
        """Draw the parameter list, dimming what cannot be edited.
        Args:
            box (curses.window): the framed window
            layout (Layout): the sizes to draw with
            lines (List[str]): the rendered lines
            column (int): the column the pane starts at
        """
        views = self.views()
        width = layout.right_width if layout.two_pane else layout.width - 2
        for index, text in enumerate(lines):
            field_index = index + self.field_top
            selected = self.pane is PANE_FIELDS and field_index == self.field_index
            if selected:
                attr = self.attr(panes.PAIR_SELECT, bold=True)
            elif field_index < len(views) and views[field_index].state is not FieldState.NORMAL:
                attr = self.attr(panes.PAIR_DIM)
            else:
                attr = self.attr(panes.PAIR_PANE)
            self._put(box, index + 1, column + 1, text.ljust(width), width, attr)

    def _draw_footer(self, screen: "curses.window", layout: Layout) -> None:
        """Draw the status line and the key bar, below the box.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
        """
        below = layout.pane_rows + layout.help_rows + 3
        status = self.message or panes.render_status(self.model)
        if status:
            self._put(screen, below, 1, status, layout.width - 2,
                      self.attr(panes.PAIR_PANE, bold=True))
        keys = panes.render_keys(self.model, self.editing is not None)
        self._put(screen, min(layout.height - 1, below + 1), 0, keys.ljust(layout.width),
                  layout.width, self.attr(panes.PAIR_KEYS, bold=True))

    def _put(self, window: "curses.window", row: int, column: int, text: str, width: int,
             attr: int = curses.A_NORMAL) -> None:
        """Write one line, without ever drawing outside the window.
        Args:
            window (curses.window): the window to draw on
            row (int): row inside that window
            column (int): column inside that window
            text (str): the text
            width (int): columns available
            attr (int): the curses attribute
        """
        height, max_width = window.getmaxyx()
        if row >= height or column >= max_width:
            return
        room = min(width, max_width - column - 1)
        if room <= 0:
            return
        try:
            window.addnstr(row, column, text, room, attr)
        except curses.error:
            pass


def _clamp_top(top: int, index: int, rows: int, total: int) -> int:
    """Keep a scroll offset so the cursor stays visible.
    Args:
        top (int): current first visible index
        index (int): index of the cursor
        rows (int): visible rows
        total (int): number of items
    Returns:
        int: the new first visible index
    """
    if total <= rows:
        return 0
    top = min(top, max(total - rows, 0))
    if index < top:
        return index
    if index >= top + rows:
        return index - rows + 1
    return top


def use_colour(no_color_flag: bool) -> bool:
    """Decide whether the scheme is painted.
    It follows smfc-client: the flag wins, and a terminal that is not a terminal gets no colour.
    Args:
        no_color_flag (bool): the --no-color flag
    Returns:
        bool: True when the scheme should be painted
    """
    if no_color_flag:
        return False
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def run(model: EditorModel, no_color: bool = False) -> int:
    """Run the editor until the user quits.
    Args:
        model (EditorModel): the configuration file to edit
        no_color (bool): True to draw without colour
    Returns:
        int: the exit code of smfc-config
    """
    app = EditorApp(model, colour=use_colour(no_color))

    def loop(screen: "curses.window") -> None:
        curses.curs_set(0)
        screen.keypad(True)
        if app.colour and curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for pair, foreground, background in COLOURS:
                curses.init_pair(pair, foreground, background)
        else:
            app.colour = False
        while app.running:
            app.draw(screen)
            key = screen.getch()
            if key == curses.KEY_RESIZE:
                continue
            app.handle_key(key)

    curses.wrapper(loop)
    return 0


# End.
