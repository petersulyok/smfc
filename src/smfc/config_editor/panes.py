#
#   panes.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.panes: what the editor draws, as text, with no terminal code in it.
#
from dataclasses import dataclass
from typing import List, Optional

from smfc.checks import Level
from smfc.config_editor.model import EditorModel, FieldState, FieldView, Row, RowKind
from smfc.config_editor.schema import FieldKind, bool_text

# Smallest screen the two-pane layout needs. Below either figure the editor falls back to one pane.
MIN_WIDTH: int = 64
MIN_ROWS: int = 14

# The frame stops growing here. Help text wrapped over 200 columns is hard to read, and a value cell
# that wide is wasted space.
MAX_WIDTH: int = 100

# Width of the section list. The longest label is "Overview" plus the two glyph columns.
LEFT_WIDTH: int = 20

# Height of the help pane, and the rows the frame and the two lines below it always take:
# the banner, the top border, the rule that carries the Help title, the bottom border, the status
# line and the key bar.
HELP_ROWS: int = 4
FIXED_ROWS: int = 6

# Glyphs of the two columns. A check mark and a ballot X are narrow on every terminal; every other
# status glyph stays ASCII, because an ambiguous-width character shifts the rest of the line.
GLYPH_ENABLED: str = "✓"
GLYPH_DISABLED: str = "✗"
GLYPH_UNCHECKED: str = "-"
GLYPH_WARN: str = "!"
GLYPH_ERROR: str = "X"


# Colour pair numbers. The scheme follows the Debian installer: a painted banner and key bar, light
# panes, and a strong selection bar. Colour carries orientation here, so it is part of the design; the
# glyphs still say the same thing on a terminal that has no colour.
PAIR_BANNER: int = 1        # the title line: white on blue
PAIR_PANE: int = 2          # the panes: black on light grey
PAIR_SELECT: int = 3        # the cursor row: white on blue
PAIR_TITLE: int = 4         # a pane title in its border: blue on light grey
PAIR_KEYS: int = 5          # the key bar: black on cyan
PAIR_OK: int = 6            # an enabled section
PAIR_WARN: int = 7          # a warning finding
PAIR_ERROR: int = 8         # an error finding
PAIR_DIM: int = 9           # an inactive or unknown parameter
PAIR_POPUP: int = 10        # a popup window
PAIR_SELECT_DIM: int = 11   # the selected row of the pane that does not have the keyboard

# Rows the frame always takes: the banner, the two pane borders and the key bar.
FRAME_ROWS: int = 4


@dataclass
class Layout:
    """Sizes the editor draws with, computed from the terminal size."""
    width: int              # Width of the frame
    height: int             # Height of the whole screen
    two_pane: bool          # False when the screen is too small for the section list beside the fields
    left_width: int         # Width of the section list
    right_width: int        # Width of the parameter list
    pane_rows: int          # Rows available inside a pane
    help_rows: int          # Rows of the help pane


def layout_for(width: int, height: int) -> Layout:
    """Compute the layout for a terminal size.
    Every extra row goes to the panes and every extra column to the parameter list. The help pane keeps
    its height, because a pane that changes height as the cursor moves is hard to read.
    Args:
        width (int): terminal width in columns
        height (int): terminal height in rows
    Returns:
        Layout: the sizes to draw with
    """
    frame_width = min(max(width, 1), MAX_WIDTH)
    two_pane = width >= MIN_WIDTH and height >= MIN_ROWS
    help_rows = HELP_ROWS if height >= 12 else 2
    pane_rows = max(height - help_rows - FIXED_ROWS, 1)
    left = LEFT_WIDTH if two_pane else frame_width - 4
    right = frame_width - left - 5 if two_pane else frame_width - 4
    return Layout(width=frame_width, height=height, two_pane=two_pane, left_width=left,
                  right_width=max(right, 1), pane_rows=pane_rows, help_rows=help_rows)


def glyph_columns(layout: Layout) -> tuple:
    """Column of the enabled glyph and of the check glyph inside a section line.
    The two are drawn in their own colour, so the caller has to know where they are. This is the only
    place that knows the shape of the line.
    Args:
        layout (Layout): the sizes to draw with
    Returns:
        tuple: the two column offsets
    """
    name_width = layout.left_width - 8
    return name_width + 3, name_width + 6


def box_rows(layout: Layout) -> int:
    """Height of the box that holds the two panes and the help.
    Args:
        layout (Layout): the sizes to draw with
    Returns:
        int: rows, the two borders and the rule included
    """
    return layout.pane_rows + layout.help_rows + 3


def footer_rows(layout: Layout) -> tuple:
    """Screen rows of the status line and of the key bar.
    They sit below the box, and the box starts one row below the banner. This is the only place that
    knows that, so a change of the frame cannot leave the status line drawn on a border.
    Args:
        layout (Layout): the sizes to draw with
    Returns:
        tuple: the status row and the key bar row
    """
    below = 1 + box_rows(layout)
    return below, below + 1


def fit(text: str, width: int) -> str:
    """Cut a line to the width of its pane, keeping the end of the text.
    The tail of a device name is its serial number, which is the only part that tells two identical
    disks apart, so the middle is dropped rather than the end.
    Args:
        text (str): the line
        width (int): columns available
    Returns:
        str: the line, at most `width` columns wide
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    keep = width - 3
    head = keep // 2
    return text[:head] + "..." + text[len(text) - (keep - head):]


def check_glyph(model: EditorModel, row: Row) -> str:
    """Render the check column of one row.
    A disabled section is never checked, so it gets no glyph at all rather than a green one. A fresh
    file that has not been checked yet shows "not checked", not an error.
    Args:
        model (EditorModel): the editor state
        row (Row): the row
    Returns:
        str: one character, or a space
    """
    if row.kind is RowKind.SEPARATOR:
        return " "
    if row.kind is not RowKind.OVERVIEW and row.toggleable and not row.enabled:
        return " "
    if not model.checked:
        return GLYPH_UNCHECKED
    level = model.worst_level(row)
    if level is Level.ERROR:
        return GLYPH_ERROR
    if level is Level.WARN:
        return GLYPH_WARN
    return " " if level is None else GLYPH_UNCHECKED


def enabled_glyph(row: Row) -> str:
    """Render the enabled column of one row.
    Args:
        row (Row): the row
    Returns:
        str: a check mark, a ballot X, or a space for a section that has no enabled= parameter
    """
    if row.kind in (RowKind.SEPARATOR, RowKind.OVERVIEW) or not row.toggleable:
        return " "
    return GLYPH_ENABLED if row.enabled else GLYPH_DISABLED


def render_sections(model: EditorModel, selected: int, top: int, layout: Layout) -> List[str]:
    """Render the section list.
    Args:
        model (EditorModel): the editor state
        selected (int): index of the selected row
        top (int): index of the first row shown
        layout (Layout): the sizes to draw with
    Returns:
        List[str]: one line per visible row
    """
    lines: List[str] = []
    for index in range(top, min(top + layout.pane_rows, len(model.rows))):
        row = model.rows[index]
        if row.kind is RowKind.SEPARATOR:
            lines.append("  " + "-" * max(layout.left_width - 4, 1))
            continue
        cursor = ">" if index == selected else " "
        name = fit(row.name, layout.left_width - 8)
        lines.append(f"{cursor} {name:<{layout.left_width - 8}} {enabled_glyph(row)}  "
                     f"{check_glyph(model, row)}")
    return lines


def render_fields(views: List[FieldView], selected: int, top: int, layout: Layout,
                  editing: Optional[str] = None) -> List[str]:
    """Render the parameter list of the selected section.
    Args:
        views (List[FieldView]): the parameters to show
        selected (int): index of the selected parameter
        top (int): index of the first parameter shown
        layout (Layout): the sizes to draw with
        editing (Optional[str]): the text being typed, when a value is open for editing
    Returns:
        List[str]: one line per visible parameter
    """
    lines: List[str] = []
    label_width = label_column(views, layout)
    for index in range(top, min(top + layout.pane_rows, len(views))):
        view = views[index]
        value_width = layout.right_width - label_width - 2
        if editing is not None and index == selected:
            value = fit(f"[{editing}]", value_width)
        else:
            value = fit(_display_value(view), value_width)
        mark = " " if view.state is FieldState.NORMAL else "~"
        # A key is cut at its end, not in the middle: the head is what tells two keys apart.
        label = view.key[:label_width]
        lines.append(f"{mark}{label:<{label_width}} {value}")
    return lines


def label_column(views: List[FieldView], layout: Layout) -> int:
    """Width of the parameter name column, sized to the section that is shown.
    The longest name of the whole file is `standby_guard_enabled` at 21 characters, so a fixed column
    would either waste space in most sections or cut that one. Half the pane is the upper bound.
    Args:
        views (List[FieldView]): the parameters to show
        layout (Layout): the sizes to draw with
    Returns:
        int: columns for the parameter name
    """
    longest = max((len(v.key) for v in views), default=8)
    return max(min(longest, layout.right_width // 2), 8)


def render_help(model: EditorModel, row: Row, view: Optional[FieldView], layout: Layout) -> List[str]:
    """Render the help pane.
    The help follows the cursor and does not wait for an edit, so a user who is only looking around
    learns what a parameter does before touching it.
    Args:
        model (EditorModel): the editor state
        row (Row): the selected row
        view (Optional[FieldView]): the selected parameter, or None when the cursor is in the left pane
        layout (Layout): the sizes to draw with
    Returns:
        List[str]: exactly `layout.help_rows` lines
    """
    width = layout.width - 4
    if view is not None and view.field is not None:
        head = f"{view.key}   {view.field.summary}"
        detail = view.field.detail
        last = view.field.range_text()
        if view.reason:
            # An invalid value or an overridden one explains itself, in place of the range line.
            last = f"error: {view.reason}" if view.state is FieldState.INVALID else view.reason
    elif view is not None:
        head = f"{view.key}   a parameter smfc does not know"
        detail = "It is kept as it is and never deleted. smfc ignores it."
        last = view.reason
    else:
        head, detail, last = _section_help(model, row)
    findings = model.findings_of(row)
    if findings:
        last = f"{findings[0].level.value}: {findings[0].message}"
    body = _wrap(detail, width, layout.help_rows - 2)
    lines = [fit(head, width)] + body + [fit(last, width)]
    return (lines + [""] * layout.help_rows)[:layout.help_rows]


def render_keys(model: EditorModel, editing: bool) -> str:
    """Render the key line, which changes with the context.
    Args:
        model (EditorModel): the editor state
        editing (bool): True while a value is open for editing
    Returns:
        str: the key list
    """
    if editing:
        return "  Enter accept   Esc cancel"
    save = "F2 save" if not model.read_only else "read-only"
    return f"  Tab pane   Enter edit   Space toggle   F5 test hardware   {save}   F10 quit"


def render_status(model: EditorModel) -> str:
    """Render the one-line state of the file, shown above the key line when it has something to say.
    Args:
        model (EditorModel): the editor state
    Returns:
        str: the message, empty when there is nothing to say
    """
    if model.read_only:
        return f"read-only: {model.path} is not writable by this user; re-run as: sudo smfc-config"
    if model.dirty:
        return "unsaved changes"
    return ""


# -- internals -------------------------------------------------------------------------------------

def _display_value(view: FieldView) -> str:
    """Render a value for the parameter list.
    Args:
        view (FieldView): the parameter
    Returns:
        str: a single-line rendering, with a device list shown as a count
    """
    if "\n" in view.value:
        count = len([line for line in view.value.splitlines() if line.strip()])
        return f"{count} devices..."
    if view.field is not None and view.field.kind is FieldKind.BOOL:
        return bool_text(view.value)
    if view.field is not None and view.field.choices and view.field.labels:
        for choice, label in zip(view.field.choices, view.field.labels):
            if str(choice) == view.value.strip():
                return f"{view.value}  {label}"
    return view.value


def _section_help(model: EditorModel, row: Row) -> tuple:
    """Build the three parts of the help pane for a section row.
    Args:
        model (EditorModel): the editor state
        row (Row): the selected row
    Returns:
        tuple: the head line, the detail text and the last line
    """
    from smfc.config_editor.schema import section_of  # pylint: disable=import-outside-toplevel
    if row.kind is RowKind.OVERVIEW:
        return ("Overview   findings that belong to no section",
                "It also names hardware this machine has and no section covers.",
                "press F5 to test the hardware" if not model.checked else "")
    section = section_of(row.family)
    if section is None:
        return (row.name, "", "")
    state = "always active" if not row.toggleable else ("enabled" if row.enabled else "disabled")
    if row.kind is RowKind.ABSENT:
        state = "not in the file, which reads as disabled"
    return f"{row.name}   {section.summary}", section.detail, state


def _wrap(text: str, width: int, rows: int) -> List[str]:
    """Wrap a text into a fixed number of lines.
    Args:
        text (str): the text
        width (int): columns available
        rows (int): lines to produce
    Returns:
        List[str]: exactly `rows` lines, padded with empty ones
    """
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return (lines + [""] * rows)[:max(rows, 0)]


# End.
