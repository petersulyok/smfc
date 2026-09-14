#
#   app.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.app: the curses loop of smfc-config.
#
import curses
from typing import List, Optional

from smfc.config_editor import panes
from smfc.config_editor.model import EditorModel, FieldView, Row
from smfc.config_editor.panes import Layout
from smfc.config_editor.schema import Widget

# Colour pairs. The editor stays readable without colour, so every one of them is decoration.
PAIR_CURSOR: int = 1        # The selected row
PAIR_ERROR: int = 2         # An error finding
PAIR_WARN: int = 3          # A warning finding
PAIR_DIM: int = 4           # An inactive or unknown parameter

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

    def __init__(self, model: EditorModel) -> None:
        """Build the screen state of one configuration file.
        Args:
            model (EditorModel): the configuration file to edit
        """
        self.model = model
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

    def draw(self, screen: "curses.window") -> None:
        """Draw the whole screen.
        Args:
            screen (curses.window): the curses screen
        """
        height, width = screen.getmaxyx()
        layout = panes.layout_for(width, height)
        self.scroll(layout)
        screen.erase()
        views = self.views()
        left = panes.render_sections(self.model, self.row_index, self.row_top, layout)
        right = panes.render_fields(views, self.field_index, self.field_top, layout, self.editing)
        if layout.two_pane:
            self._draw_two_panes(screen, layout, left, right)
        else:
            self._draw_one_pane(screen, layout, left if self.pane is PANE_SECTIONS else right)
        self._draw_help(screen, layout, views)
        screen.noutrefresh()
        curses.doupdate()

    def _draw_two_panes(self, screen: "curses.window", layout: Layout, left: List[str],
                        right: List[str]) -> None:
        """Draw the section list beside the parameter list.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
            left (List[str]): the rendered section list
            right (List[str]): the rendered parameter list
        """
        divider = layout.left_width + 1
        screen.vline(0, divider, curses.ACS_VLINE, layout.pane_rows)
        for index, text in enumerate(left):
            self._put(screen, index, 0, text, layout.left_width,
                      selected=self.pane is PANE_SECTIONS and index + self.row_top == self.row_index)
        for index, text in enumerate(right):
            self._put(screen, index, divider + 2, text, layout.right_width,
                      selected=self.pane is PANE_FIELDS and index + self.field_top == self.field_index)

    def _draw_one_pane(self, screen: "curses.window", layout: Layout, lines: List[str]) -> None:
        """Draw a single pane, used when the terminal is too small for two.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
            lines (List[str]): the rendered lines of the pane that has the cursor
        """
        selected = self.row_index - self.row_top if self.pane is PANE_SECTIONS \
            else self.field_index - self.field_top
        for index, text in enumerate(lines):
            self._put(screen, index, 0, text, layout.width - 1, selected=index == selected)

    def _draw_help(self, screen: "curses.window", layout: Layout, views: List[FieldView]) -> None:
        """Draw the divider, the help pane, the status line and the key line.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
            views (List[FieldView]): the parameters of the selected section
        """
        top = layout.pane_rows
        screen.hline(top, 0, curses.ACS_HLINE, layout.width)
        view = self.view() if views else None
        for index, text in enumerate(panes.render_help(self.model, self.row, view, layout)):
            self._put(screen, top + 1 + index, 0, text, layout.width - 1)
        status = self.message or panes.render_status(self.model)
        self._put(screen, top + 1 + layout.help_rows, 0, status, layout.width - 1)
        self._put(screen, min(layout.height - 1, top + 2 + layout.help_rows), 0,
                  panes.render_keys(self.model, self.editing is not None), layout.width - 1)

    def _put(self, screen: "curses.window", row: int, column: int, text: str, width: int,
             selected: bool = False) -> None:
        """Write one line, without ever drawing outside the window.
        Args:
            screen (curses.window): the curses screen
            row (int): screen row
            column (int): screen column
            text (str): the text
            width (int): columns available
            selected (bool): True to highlight the line
        """
        height, max_width = screen.getmaxyx()
        if row >= height or column >= max_width:
            return
        room = min(width, max_width - column - 1)
        if room <= 0:
            return
        try:
            screen.addnstr(row, column, text, room, curses.A_REVERSE if selected else curses.A_NORMAL)
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


def run(model: EditorModel) -> int:
    """Run the editor until the user quits.
    Args:
        model (EditorModel): the configuration file to edit
    Returns:
        int: the exit code of smfc-config
    """
    app = EditorApp(model)

    def loop(screen: "curses.window") -> None:
        curses.curs_set(0)
        screen.keypad(True)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(PAIR_CURSOR, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(PAIR_ERROR, curses.COLOR_RED, -1)
            curses.init_pair(PAIR_WARN, curses.COLOR_YELLOW, -1)
            curses.init_pair(PAIR_DIM, curses.COLOR_BLUE, -1)
        while app.running:
            app.draw(screen)
            key = screen.getch()
            if key == curses.KEY_RESIZE:
                continue
            app.handle_key(key)

    curses.wrapper(loop)
    return 0


# End.
