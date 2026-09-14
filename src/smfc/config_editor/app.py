#
#   app.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.app: the curses loop of smfc-config.
#
import curses
import sys
from typing import List, Optional

from smfc.config_editor import panes, popups
from smfc.config_editor.lineedit import LineEdit
from smfc.config_editor.model import EditorModel, FieldState, FieldView, Row, RowKind
from smfc.config_editor.panes import Layout
from smfc.config_editor.schema import SECTIONS, FieldKind, Widget, bool_text, bool_value, validate
from smfc.discover import discover_hds, discover_nvmes

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
    (panes.PAIR_SELECT_DIM, curses.COLOR_BLUE, curses.COLOR_WHITE),
    (panes.PAIR_INPUT, curses.COLOR_WHITE, curses.COLOR_BLUE),
)

# The standing status line already says the file is read-only. A blocked key has to say something
# else, or the screen does not change and the key looks dead. It names the way out instead.
READ_ONLY_MESSAGE = "this file belongs to root; quit with F10 and run: sudo smfc-config"

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
    editing: Optional[LineEdit]     # The value being typed, None when not editing
    message: str                    # One line of feedback, shown until the next key
    running: bool                   # False once the user has quit
    colour: bool                    # True when the terminal paints the scheme
    popup: Optional[popups.Popup]   # The window over the panes, None when there is none
    pending: Optional[popups.Popup] # The selector waiting under an add-by-path field
    cursor_at: Optional[tuple]      # Where the terminal cursor goes while typing, None when idle

    def __init__(self, model: EditorModel, colour: bool = True) -> None:
        """Build the screen state of one configuration file.
        Args:
            model (EditorModel): the configuration file to edit
            colour (bool): False to draw without colour
        """
        self.model = model
        self.colour = colour
        self.popup = None
        self.pending = None
        self.pane = PANE_SECTIONS
        self.row_index = 0
        self.row_top = 0
        self.field_index = 0
        self.field_top = 0
        self.editing = None
        self.message = ""
        self.running = True
        self.cursor_at = None

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
            self.message = READ_ONLY_MESSAGE
            return
        if view.field is None:
            self.message = "smfc does not know this parameter; it is kept as it is"
            return
        self._open_widget(view)

    def _open_widget(self, view: FieldView) -> None:
        """Open the widget one parameter is edited with.
        Args:
            view (FieldView): the parameter under the cursor
        """
        if view.field.kind is FieldKind.BOOL:
            # A boolean has two values, so it is switched rather than typed, the same way a section is.
            new_value = bool_value(bool_text(view.value) == "no")
            self.model.set_value(self.row, view.key, new_value)
            self.message = f"{view.key} = {bool_text(new_value)}"
            return
        if view.field.widget is Widget.INLINE:
            self.editing = LineEdit.of(view.value)
            return
        if view.field.widget is Widget.SELECT:
            self.popup = popups.ChoicePopup(
                title=view.key, width=54, summary=view.field.summary,
                choices=[str(c) for c in view.field.choices],
                labels=[str(label) for label in view.field.labels],
                index=_choice_index(view))
            return
        if view.field.widget is Widget.DEVICES and view.field.kind is FieldKind.DEVICE_LIST:
            self.popup = self._device_popup(view)
            return
        self.popup = popups.TextPopup(
            title=view.key, width=72, text=view.value.replace("\n", " ").replace("\t", " ").strip(),
            summary=view.field.summary, detail=view.field.range_text(),
            validator=lambda text, f=view.field: validate(f, text))

    def _device_popup(self, view: FieldView) -> popups.DevicePopup:
        """Build the device selector of one list parameter.
        The devices of the machine come from smfc.discover, the same two functions the installer uses.
        An entry the file lists and the machine does not have is kept and marked, because that is what
        explains a warning about a missing disk.
        Args:
            view (FieldView): the parameter being edited
        Returns:
            popups.DevicePopup: the selector
        """
        listed = [line.strip() for line in view.value.splitlines() if line.strip()]
        found = discover_hds() if view.key == "hd_names" else discover_nvmes()
        entries = [popups.DeviceEntry(path=path, label=_device_label(path), ticked=path in listed)
                   for path in found]
        for path in listed:
            if path not in found:
                entries.append(popups.DeviceEntry(path=path, label=f"(missing)  {path.split('/')[-1]}",
                                                  ticked=True, present=False))
        return popups.DevicePopup(title=view.key, width=72, entries=entries,
                                  note="p adds a device this machine does not have yet")

    def finish_edit(self, accept: bool) -> None:
        """Close the editor of one parameter.
        Args:
            accept (bool): True to write the typed value, False to drop it
        """
        view = self.view()
        if accept and view is not None and self.editing is not None:
            self.model.set_value(self.row, view.key, self.editing.text.strip())
            self.message = f"{view.key} = {self.editing.text.strip()}"
        self.editing = None

    def toggle(self) -> None:
        """Switch the selected family on or off."""
        if self.model.read_only:
            self.message = READ_ONLY_MESSAGE
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
        """Run every check, the ones that talk to the hardware included.
        A probe costs seconds, so the screen says what is happening before the keyboard stops
        answering.
        """
        self.message = "testing the hardware..."
        self.model.run_checks(hardware=True)
        findings = sum(len(v) for v in self.model.findings.values())
        self.message = (f"checked, {findings} findings" if not self.model.has_errors()
                        else f"checked, {findings} findings, errors found")

    # -- keys --------------------------------------------------------------------------------------

    def handle_key(self, key: int) -> None:
        """Act on one key press.
        Args:
            key (int): the key, as curses reports it
        """
        if self.popup is not None and key != -1:
            self._handle_popup_key(key)
            return
        if key == -1:
            # The terminal has gone away: getch() answers at once instead of waiting, so carrying on
            # would spin on one core for as long as the process lives.
            self.running = False
            return
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
        elif key in (curses.KEY_F6, ord("+")):
            self.add_instance()
        elif key in (curses.KEY_F8, ord("-")):
            self.remove_instance()

    def _move(self, step: int) -> None:
        """Move the cursor of whichever pane it is in.
        Args:
            step (int): -1 for up, 1 for down
        """
        if self.pane is PANE_SECTIONS:
            self.move_row(step)
        else:
            self.move_field(step)

    def _handle_popup_key(self, key: int) -> None:
        """Give one key to the popup, and apply its answer when it closes.
        Args:
            key (int): the key, as curses reports it
        """
        popup = self.popup
        if isinstance(popup, popups.DevicePopup) and key == ord("p"):
            self.popup = popups.TextPopup(
                title="add a device by path", width=72, text="/dev/disk/by-id/",
                summary="A device this machine does not have yet is kept and marked missing.",
                detail="the /dev/disk/by-id/ form, which survives a reboot",
                validator=_validate_device_path)
            self.pending = popup
            return
        popup.handle_key(key)
        if not popup.done:
            return
        self.popup = None
        if isinstance(popup, popups.TextPopup) and self.pending is not None:
            selector, self.pending = self.pending, None
            if popup.accepted:
                selector.add_path(popup.value())
            self.popup = selector
            return
        if popup.accepted:
            self._apply_popup(popup)

    def _apply_popup(self, popup: popups.Popup) -> None:
        """Write what a popup answered.
        Args:
            popup (popups.Popup): the popup that has just closed
        """
        if isinstance(popup, popups.InstancePopup):
            family, zone = popup.value()
            name = self.model.add_instance(family, {"enabled": "1", "ipmi_zone": str(zone)})
            self.row_index = [i for i, r in enumerate(self.model.rows) if r.name == name][0]
            self.message = f"[{name}] added on zone {zone}"
            return
        if isinstance(popup, popups.ConfirmPopup):
            name = self.row.name
            self.model.remove_instance(self.row)
            self.row_index = min(self.row_index, len(self.model.rows) - 1)
            self.message = f"[{name}] removed"
            return
        view = self.view()
        if view is None:
            return
        if isinstance(popup, popups.DevicePopup):
            self.model.set_device_list(self.row, view.key, popup.value())
            self.message = f"{view.key}: {len(popup.value())} devices"
            self.model.run_checks()
            return
        self.model.set_value(self.row, view.key, popup.value())
        self.message = f"{view.key} = {popup.value()}"

    def add_instance(self) -> None:
        """Open the dialog that adds one more fan curve to a family."""
        if self.model.read_only:
            self.message = READ_ONLY_MESSAGE
            return
        families = [name for name, section in SECTIONS.items() if section.repeatable]
        self.popup = popups.InstancePopup(
            title="add an instance", width=54, families=families,
            zones=self.model.free_zones(families[0]),
            on_family=self.model.free_zones)

    def remove_instance(self) -> None:
        """Ask before removing the selected instance."""
        if self.model.read_only:
            self.message = READ_ONLY_MESSAGE
            return
        if self.row.kind is not RowKind.INSTANCE or ":" not in self.row.name:
            self.message = "only a numbered instance can be removed"
            return
        self.popup = popups.ConfirmPopup(
            title="remove an instance", width=54,
            question=f"Remove [{self.row.name}] from the file?",
            detail="Its own values are lost. The other instances are untouched.")

    def _handle_edit_key(self, key: int) -> None:
        """Act on one key press while a value is open for editing.
        Args:
            key (int): the key, as curses reports it
        """
        if key in (curses.KEY_ENTER, 10, 13):
            self.finish_edit(True)
        elif key == 27:
            self.finish_edit(False)
        elif self.editing is not None:
            self.editing.handle_key(key)

    # -- drawing -----------------------------------------------------------------------------------

    def attr(self, pair: int, bold: bool = False) -> int:
        """Build the attribute of one colour role.
        Without colour the selection and the input field fall back to reverse video, so both stay visible.
        Args:
            pair (int): the colour pair number
            bold (bool): True to add bold
        Returns:
            int: the curses attribute
        """
        if not self.colour:
            base = curses.A_REVERSE if pair in (panes.PAIR_SELECT, panes.PAIR_BANNER,
                                                panes.PAIR_KEYS, panes.PAIR_INPUT) else curses.A_NORMAL
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
        self.cursor_at = None
        views = self.views()
        self._draw_banner(screen, layout)
        self._draw_panes(screen, layout, views)
        self._draw_footer(screen, layout)
        if self.popup is not None:
            self._draw_popup(screen, layout)
        self._place_cursor(screen, height, width)
        screen.noutrefresh()
        curses.doupdate()

    def _place_cursor(self, screen: "curses.window", height: int, width: int) -> None:
        """Show the terminal cursor where the next character will land, and hide it otherwise.
        A user typing needs to see where the text goes. The cursor is the only mark that says it, so
        it appears while a value is open and disappears as soon as the value is closed.
        Args:
            screen (curses.window): the curses screen
            height (int): rows of the screen
            width (int): columns of the screen
        """
        try:
            if self.cursor_at is None:
                curses.curs_set(0)
                return
            row, column = self.cursor_at
            # A thin caret inserts, a block caret types over. This is what a terminal editor does, so
            # the shape alone says which mode the field is in.
            curses.curs_set(1 if self._insert_mode() else 2)
            screen.move(min(row, height - 1), min(column, width - 1))
        except curses.error:
            # A terminal that cannot show or hide the cursor is not a reason to stop drawing.
            pass

    def _insert_mode(self) -> bool:
        """Whether the field being typed into is in insert mode.
        Returns:
            bool: True to push the text along, False to type over it
        """
        if isinstance(self.popup, popups.TextPopup):
            return self.popup.line.insert
        return self.editing is None or self.editing.insert

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
        box = screen.derwin(panes.box_rows(layout), layout.width, 1, 0)
        box.bkgd(" ", self.attr(panes.PAIR_PANE))
        box.box()
        box.hline(rule, 1, curses.ACS_HLINE, layout.width - 2)
        box.addch(rule, 0, curses.ACS_LTEE)
        box.addch(rule, layout.width - 1, curses.ACS_RTEE)
        self._put(box, rule, 2, " Help ", 6, self.attr(panes.PAIR_TITLE, bold=True))

        left = panes.render_sections(self.model, self.row_index, self.row_top, layout)
        right = panes.render_fields(views, self.field_index, self.field_top, layout,
                                    self.editing is not None)
        if layout.two_pane:
            divider = layout.left_width + 1
            box.vline(1, divider, curses.ACS_VLINE, layout.pane_rows)
            box.addch(0, divider, curses.ACS_TTEE)
            box.addch(rule, divider, curses.ACS_BTEE)
            left_focus = self.pane is PANE_SECTIONS
            self._put(box, 0, 2, " Sections ", 10, self._title_attr(left_focus))
            title = f" [{self.row.name}] "
            self._put(box, 0, divider + 2, title, len(title), self._title_attr(not left_focus))
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

    def _title_attr(self, focused: bool) -> int:
        """Attribute of a pane title, so the border says which pane has the keyboard.
        Args:
            focused (bool): True for the pane the cursor is in
        Returns:
            int: the curses attribute
        """
        return self.attr(panes.PAIR_BANNER if focused else panes.PAIR_TITLE, bold=True)

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
            cursor = row_index == self.row_index
            focused = cursor and self.pane is PANE_SECTIONS
            if focused:
                base = self.attr(panes.PAIR_SELECT, bold=True)
            elif cursor:
                base = self.attr(panes.PAIR_SELECT_DIM, bold=True)
            else:
                base = self.attr(panes.PAIR_PANE)
            self._put(box, index + 1, column, text.ljust(layout.left_width), layout.left_width, base)
            if focused:
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
            cursor = field_index == self.field_index
            if cursor and self.editing is not None and self.pane is PANE_FIELDS:
                # The field below carries the highlight while a value is typed, so the row around it
                # stays plain and the field is the only painted part of the line.
                attr = self.attr(panes.PAIR_PANE)
            elif cursor and self.pane is PANE_FIELDS:
                attr = self.attr(panes.PAIR_SELECT, bold=True)
            elif cursor:
                attr = self.attr(panes.PAIR_SELECT_DIM, bold=True)
            elif field_index < len(views) and views[field_index].state is FieldState.INVALID:
                attr = self.attr(panes.PAIR_ERROR, bold=True)
            elif field_index < len(views) and views[field_index].state is not FieldState.NORMAL:
                attr = self.attr(panes.PAIR_DIM)
            else:
                attr = self.attr(panes.PAIR_PANE)
            self._put(box, index + 1, column + 1, text.ljust(width), width, attr)
            if cursor and self.editing is not None and self.pane is PANE_FIELDS:
                self._draw_input(box, layout, index + 1, column + 1, width)

    def _draw_input(self, box: "curses.window", layout: Layout, row: int, column: int,
                    width: int) -> None:
        """Paint the field a value is typed into, and note where the caret goes.
        The field is a block of its own colour rather than a value in brackets: a user reading the
        screen sees the extent of the field without decoding a character.
        Args:
            box (curses.window): the framed window
            layout (Layout): the sizes to draw with
            row (int): row of the parameter inside the box
            column (int): column the parameter pane starts at
            width (int): width of one line of that pane
        """
        label_width = panes.label_column(self.views(), layout)
        start = column + label_width + 2
        field_width = max(width - label_width - 2, 1)
        text, caret = self.editing.view(field_width)
        self._put(box, row, start, text, field_width, self.attr(panes.PAIR_INPUT))
        # The box sits one row below the banner, so a row inside it is one row further down the screen.
        self.cursor_at = (row + 1, start + caret)

    def _draw_footer(self, screen: "curses.window", layout: Layout) -> None:
        """Draw the status line and the key bar, below the box.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
        """
        status_row, keys_row = panes.footer_rows(layout)
        status = self.message or panes.render_status(self.model)
        if status:
            self._put(screen, status_row, 1, status, layout.width - 2,
                      self.attr(panes.PAIR_PANE, bold=True))
        keys = panes.render_keys(self.model, self.editing is not None)
        self._put(screen, min(layout.height - 1, keys_row), 0, keys.ljust(layout.width),
                  layout.width, self.attr(panes.PAIR_KEYS, bold=True))

    def _draw_popup(self, screen: "curses.window", layout: Layout) -> None:
        """Draw the window that is open over the panes.
        Args:
            screen (curses.window): the curses screen
            layout (Layout): the sizes to draw with
        """
        popup = self.popup
        body = popup.lines()
        width = min(popup.width, layout.width - 2)
        height = min(len(body) + 4, layout.height - 2)
        top = max((layout.height - height) // 2, 0)
        left = max((layout.width - width) // 2, 0)
        window = screen.derwin(height, width, top, left)
        window.bkgd(" ", self.attr(panes.PAIR_POPUP))
        # A derived window shares the memory of the screen, and bkgd() only sets the background
        # attribute. Without the erase every cell the popup does not write keeps what the panes drew
        # underneath, and the window fills with pieces of the section list and the parameter list.
        window.erase()
        window.box()
        title = f" {popup.title} "
        self._put(window, 0, 2, title, len(title), self.attr(panes.PAIR_POPUP, bold=True))
        for index, text in enumerate(body[:height - 4]):
            selected = index == popup.cursor()
            attr = self.attr(panes.PAIR_SELECT, bold=True) if selected else \
                self.attr(panes.PAIR_ERROR if text.startswith("!") else panes.PAIR_POPUP)
            self._put(window, index + 1, 2, text.ljust(width - 4), width - 4, attr)
        if popup.error and not any(line.startswith("!") for line in body):
            self._put(window, height - 3, 2, f"! {popup.error}", width - 4,
                      self.attr(panes.PAIR_ERROR))
        self._put(window, height - 2, 2, popup.keys(), width - 4, self.attr(panes.PAIR_POPUP))
        if isinstance(popup, popups.TextPopup):
            field_width = width - 4
            text, caret = popup.line.view(field_width)
            row = popup.INPUT_ROW + 1
            self._put(window, row, 2, text, field_width, self.attr(panes.PAIR_INPUT))
            self.cursor_at = (top + row, left + 2 + caret)

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


def _choice_index(view: FieldView) -> int:
    """Index of the value a parameter currently holds, among the values it accepts.
    Args:
        view (FieldView): the parameter being edited
    Returns:
        int: the index, 0 when the value is not one of the choices
    """
    choices = [str(choice) for choice in view.field.choices]
    return choices.index(view.value.strip()) if view.value.strip() in choices else 0


def _device_label(path: str) -> str:
    """Build the line of one device in the selector.
    The serial leads, because a machine can hold eight disks of one model and the serial is the only
    part that tells them apart. The model follows it, to separate two makes of drive.
    Args:
        path (str): the /dev/disk/by-id/... path
    Returns:
        str: the line
    """
    name = path.split("/")[-1]
    body = name.split("-", 1)[1] if "-" in name else name
    serial = body.rsplit("_", 1)[-1] if "_" in body else body
    model = body[:-(len(serial) + 1)] if body.endswith(serial) and len(body) > len(serial) else ""
    return f"{serial:<14} {model.replace('_', ' ')}"


def _validate_device_path(text: str) -> str:
    """Check a device path typed by hand.
    Args:
        text (str): the path
    Returns:
        str: what is wrong with it, or an empty string
    """
    if not text.startswith("/dev/disk/by-id/"):
        return "the path must start with /dev/disk/by-id/"
    if len(text) <= len("/dev/disk/by-id/"):
        return "name the device after the prefix"
    return ""


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
