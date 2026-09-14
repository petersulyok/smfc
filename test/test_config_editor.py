#!/usr/bin/env python3
#
#   test_config_editor.py (C) 2026, Peter Sulyok
#   Unit test for the smfc.config_editor model, panes, app and cmd modules.
#
import curses
import os
import shutil
from pathlib import Path
import pytest
from smfc.checks import Level
from smfc.config_editor import panes, popups
from smfc.config_editor.app import EditorApp, PANE_FIELDS, PANE_SECTIONS
from smfc.config_editor.cmd import EXIT_CONFIG_ERROR, main
from smfc.config_editor.lineedit import LineEdit
from smfc.config_editor.model import EditorModel, FieldState, RowKind
from smfc.config_editor.schema import SECTIONS


# Repository paths used by the tests.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SHIPPED_CONF: Path = REPO_ROOT / "config" / "smfc.conf"

# A module list with nothing smfc needs in it, so the checks report what they should.
NO_MODULES: str = "usbcore 1 - Live 0x0\n"

# A small configuration with two sections.
SMALL: str = "[Ipmi]\ncommand=/usr/bin/ipmitool\n\n[CPU]\nenabled=1\nipmi_zone=0\nmin_temp=30.0\n"


def _model(tmp_path: Path, body: str = SMALL) -> EditorModel:
    """Build a model from a configuration file written for the test.
    Args:
        tmp_path (Path): pytest temporary directory
        body (str): content of the configuration file
    Returns:
        EditorModel: the model
    """
    path = tmp_path / "smfc.conf"
    path.write_text(body, encoding="utf-8")
    return EditorModel.load(str(path))


def _shipped(tmp_path: Path) -> EditorModel:
    """Build a model from a copy of the shipped configuration file.
    Args:
        tmp_path (Path): pytest temporary directory
    Returns:
        EditorModel: the model
    """
    path = tmp_path / "smfc.conf"
    shutil.copy(SHIPPED_CONF, path)
    return EditorModel.load(str(path))


def _row(model: EditorModel, name: str):
    """Find one row of the section list by name.
    Args:
        model (EditorModel): the editor state
        name (str): section or family name
    Returns:
        Row: the row
    """
    return [r for r in model.rows if r.name == name][0]


class TestEditorModel:
    """Unit test class for the smfc.config_editor.model module."""

    def test_the_section_list_holds_every_family_of_the_schema(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file that holds two sections out of nine
        - ASSERT: every family of the schema has a row, because a missing section reads as disabled
        - ASSERT: the families that are not in the file are marked absent
        - ASSERT: the list ends with a separator and the Overview row
        """
        model = _model(tmp_path)
        names = [r.name for r in model.rows if r.kind is not RowKind.SEPARATOR]
        assert set(SECTIONS) <= set(names)
        assert _row(model, "PCI").kind is RowKind.ABSENT
        assert _row(model, "CPU").kind is RowKind.INSTANCE
        assert model.rows[-1].kind is RowKind.OVERVIEW
        assert model.rows[-2].kind is RowKind.SEPARATOR

    def test_every_instance_of_a_family_is_its_own_row(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file that holds [CPU] and [CPU:1]
        - ASSERT: both are rows of their own, because each instance is a complete fan controller
        - ASSERT: there is no parent row above them
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\n[CPU:1]\nenabled=1\nipmi_zone=1\n")
        cpu_rows = [r.name for r in model.rows if r.family == "CPU"]
        assert cpu_rows == ["CPU", "CPU:1"]

    def test_the_ipmi_row_is_always_active(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file and look at the [Ipmi] row
        - ASSERT: it is not toggleable, because the section has no enabled= parameter
        - ASSERT: it still counts as enabled, so its checks run
        """
        model = _model(tmp_path)
        row = _row(model, "Ipmi")
        assert row.toggleable is False
        assert row.enabled is True

    def test_the_editor_opens_a_file_the_parser_rejects(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.run_checks(). It contains the following steps:
        - load the shipped configuration file, which the parser rejects because [HD] is enabled with
          an empty hd_names=
        - run the checks
        - ASSERT: the model still built every row, so the file can be edited
        - ASSERT: the parse failure became an error finding
        - ASSERT: the finding sits on the [HD] row, taken from the section the message names
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        assert len(model.rows) > 5
        assert model.has_errors() is True
        findings = model.findings_of(_row(model, "HD"))
        assert findings and findings[0].level is Level.ERROR
        assert "hd_names" in findings[0].message

    def test_a_curve_makes_four_parameters_inactive(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file whose [CPU] carries a control_function= value
        - ASSERT: min_temp, max_temp, min_level and max_level are inactive, because the curve wins
        - ASSERT: every other parameter stays editable
        - ASSERT: the inactive ones carry the reason, for the help pane
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\ncontrol_function=40-35, 70-100\n")
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        for key in ("min_temp", "max_temp", "min_level", "max_level"):
            assert views[key].state is FieldState.INACTIVE
            assert "control_function" in views[key].reason
        assert views["sensitivity"].state is FieldState.NORMAL

    def test_a_parameter_smfc_does_not_know_is_kept(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file that holds a parameter the schema does not define
        - ASSERT: the parameter is shown, so the user can see what is in their file
        - ASSERT: it is marked unknown, which the editor draws read-only and never deletes
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nmystery_key=42\n")
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["mystery_key"].state is FieldState.UNKNOWN
        assert views["mystery_key"].value == "42"

    def test_a_parameter_that_is_absent_shows_its_default(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file whose [CPU] names only two parameters
        - ASSERT: every other parameter is shown with the default the parser would apply
        """
        model = _model(tmp_path)
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["steps"].value == "6"
        assert views["max_temp"].value == "60.0"

    def test_toggling_a_family_keeps_its_values(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.toggle(). It contains the following steps:
        - switch [CPU] off, then read the file back
        - ASSERT: enabled=0 was written
        - ASSERT: min_temp still carries the value the user typed, because nothing was deleted
        """
        model = _model(tmp_path)
        model.toggle(_row(model, "CPU"))
        model.writer.save()
        assert model.writer.get("CPU", "enabled") == "0"
        assert model.writer.get("CPU", "min_temp") == "30.0"

    def test_the_ipmi_row_cannot_be_toggled(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.toggle(). It contains the following steps:
        - try to switch the [Ipmi] row off
        - ASSERT: the call reports that nothing was switched
        """
        model = _model(tmp_path)
        assert model.toggle(_row(model, "Ipmi")) is False

    def test_writing_to_an_absent_family_creates_its_section(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.set_value(). It contains the following steps:
        - switch on a family the file does not hold
        - ASSERT: the section is created and holds only what was written
        - ASSERT: the row becomes an instance of the file
        """
        model = _model(tmp_path)
        row = _row(model, "PCI")
        model.set_value(row, "enabled", "1")
        assert row.kind is RowKind.INSTANCE
        assert model.writer.keys("PCI") == ["enabled"]
        assert model.dirty is True

    def test_adding_an_instance_takes_the_next_free_number(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.add_instance(). It contains the following steps:
        - add two instances to a family that already holds the base section
        - ASSERT: they are numbered :1 and :2, because the suffix is only ordering
        - ASSERT: the base section is untouched
        """
        model = _model(tmp_path)
        assert model.add_instance("CPU") == "CPU:1"
        assert model.add_instance("CPU") == "CPU:2"
        assert model.writer.get("CPU", "min_temp") == "30.0"

    def test_a_family_that_takes_no_instance(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.add_instance(). It contains the following steps:
        - add an instance to [Ipmi], which is not repeatable
        - ASSERT: it raises KeyError
        """
        model = _model(tmp_path)
        with pytest.raises(KeyError):
            model.add_instance("Ipmi")

    def test_removing_an_instance(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.remove_instance(). It contains the following steps:
        - add an instance and remove it again
        - ASSERT: only the base section is left
        - ASSERT: removing a family that is not in the file raises
        """
        model = _model(tmp_path)
        model.add_instance("CPU")
        model.remove_instance(_row(model, "CPU:1"))
        assert [r.name for r in model.rows if r.family == "CPU"] == ["CPU"]
        with pytest.raises(KeyError):
            model.remove_instance(_row(model, "PCI"))

    def test_free_zones_skips_the_zones_an_enabled_instance_claims(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.free_zones(). It contains the following steps:
        - load a file whose enabled [CPU] drives zones 0 and 1, and whose disabled [CPU:1] names zone 2
        - ASSERT: zones 0 and 1 are not offered, because an enabled instance holds them
        - ASSERT: zone 2 is offered, because a disabled instance claims nothing
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nipmi_zone=0,1\n"
                                 "[CPU:1]\nenabled=0\nipmi_zone=2\n")
        assert model.free_zones("CPU", count=4) == [2, 3]

    def test_saving_a_read_only_file_is_refused(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.save(). It contains the following steps:
        - take the write rights away from the configuration file
        - ASSERT: the model reports it as read-only
        - ASSERT: saving raises PermissionError rather than losing the change quietly
        """
        path = tmp_path / "smfc.conf"
        path.write_text(SMALL, encoding="utf-8")
        os.chmod(path, 0o400)
        model = EditorModel.load(str(path))
        if os.geteuid() == 0:
            pytest.skip("root may write a read-only file")
        assert model.read_only is True
        with pytest.raises(PermissionError):
            model.save()

    def test_saving_reports_the_findings_and_clears_the_dirty_flag(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.save(). It contains the following steps:
        - change a value of the shipped configuration file and save it
        - ASSERT: the save is not blocked, although the file has an error in it
        - ASSERT: the unsaved-changes flag is cleared
        - ASSERT: the findings of the saved file are returned
        """
        model = _shipped(tmp_path)
        model.set_value(_row(model, "CPU"), "min_temp", "40.0")
        assert model.dirty is True
        findings = model.save()
        assert model.dirty is False
        assert any(f.level is Level.ERROR for f in findings)


class TestPanes:
    """Unit test class for the smfc.config_editor.panes module."""

    @pytest.mark.parametrize(
        "width, height, two_pane",
        [
            pytest.param(80, 24, True, id="a-standard-terminal"),
            pytest.param(64, 14, True, id="exactly-the-minimum"),
            pytest.param(63, 14, False, id="one-column-too-narrow"),
            pytest.param(64, 13, False, id="one-row-too-short"),
            pytest.param(200, 60, True, id="a-very-large-terminal"),
        ],
    )
    def test_the_two_pane_layout_has_a_floor(self, width: int, height: int, two_pane: bool) -> None:
        """Positive unit test for layout_for(). It contains the following steps:
        - compute the layout for terminals around the minimum size
        - ASSERT: two panes are used at 64 columns and 14 rows and above
        - ASSERT: below either figure the editor falls back to one pane instead of refusing to start
        """
        assert panes.layout_for(width, height).two_pane is two_pane

    def test_the_frame_stops_growing(self) -> None:
        """Positive unit test for layout_for(). It contains the following steps:
        - compute the layout for a very wide terminal
        - ASSERT: the frame stops at 100 columns, because wrapped help text stops being readable
        - ASSERT: every extra row goes to the panes, while the help pane keeps its height
        """
        layout = panes.layout_for(200, 60)
        assert layout.width == panes.MAX_WIDTH
        assert layout.help_rows == panes.HELP_ROWS
        assert layout.pane_rows == 60 - panes.HELP_ROWS - panes.FIXED_ROWS

    @pytest.mark.parametrize("height", [16, 20, 24, 30, 60])
    def test_the_footer_sits_below_the_box(self, height: int) -> None:
        """Positive unit test for footer_rows(). It contains the following steps:
        - compute the layout and the footer rows for several terminal heights
        - ASSERT: the status line sits on the first row below the box, not on its bottom border
        - ASSERT: the key bar sits on the last row of the terminal, with nothing under it
        """
        layout = panes.layout_for(80, height)
        status_row, keys_row = panes.footer_rows(layout)
        assert status_row == 1 + panes.box_rows(layout)
        assert keys_row == height - 1

    def test_a_long_line_is_cut_in_the_middle(self) -> None:
        """Positive unit test for fit(). It contains the following steps:
        - cut a device name that is longer than the pane
        - ASSERT: the head and the tail survive, because the serial number is at the end
        - ASSERT: the result is exactly as wide as the pane
        """
        name = "ata-WDC_WD120EFAX-68UNTN0_3A19R759"
        cut = panes.fit(name, 20)
        assert len(cut) == 20
        assert cut.startswith("ata-WDC")
        assert cut.endswith("R759")

    def test_a_disabled_section_gets_no_check_glyph(self, tmp_path: Path) -> None:
        """Positive unit test for check_glyph(). It contains the following steps:
        - run the checks on a file whose [NVME] is disabled
        - ASSERT: the disabled row shows no check glyph, rather than a green one
        - ASSERT: a row that has not been checked yet shows the not-checked glyph
        """
        model = _model(tmp_path)
        assert panes.check_glyph(model, _row(model, "CPU")) == panes.GLYPH_UNCHECKED
        model.run_checks(modules=NO_MODULES)
        assert panes.check_glyph(model, _row(model, "NVME")) == " "

    def test_an_error_shows_on_its_row(self, tmp_path: Path) -> None:
        """Positive unit test for check_glyph(). It contains the following steps:
        - run the checks on the shipped file, whose [HD] cannot be parsed
        - ASSERT: the [HD] row carries the error glyph
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        assert panes.check_glyph(model, _row(model, "HD")) == panes.GLYPH_ERROR

    def test_the_help_pane_always_has_the_same_height(self, tmp_path: Path) -> None:
        """Positive unit test for render_help(). It contains the following steps:
        - render the help of a parameter, of a section row, and of a row with a finding
        - ASSERT: each one is exactly as tall as the layout says
        - ASSERT: a parameter's help names the parameter and its summary
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        layout = panes.layout_for(80, 24)
        row = _row(model, "CPU")
        views = model.fields_of(row)
        assert len(panes.render_help(model, row, views[6], layout)) == layout.help_rows
        assert len(panes.render_help(model, row, None, layout)) == layout.help_rows
        assert views[6].key in panes.render_help(model, row, views[6], layout)[0]

    def test_the_help_pane_shows_the_finding_of_the_row(self, tmp_path: Path) -> None:
        """Positive unit test for render_help(). It contains the following steps:
        - render the help of the [HD] row of the shipped file, after the checks
        - ASSERT: the last line carries the finding, which is what the user has to act on
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        row = _row(model, "HD")
        lines = panes.render_help(model, row, None, panes.layout_for(80, 24))
        assert "hd_names" in lines[-1]

    def test_the_key_line_follows_the_context(self, tmp_path: Path) -> None:
        """Positive unit test for render_keys(). It contains the following steps:
        - render the key line while editing and while not editing
        - ASSERT: editing offers only accept and cancel
        - ASSERT: a read-only file does not offer a save key
        """
        model = _model(tmp_path)
        assert "Esc cancel" in panes.render_keys(model, True)
        assert "F2 save" in panes.render_keys(model, False)
        model.read_only = True
        assert "read-only" in panes.render_keys(model, False)

    def test_a_device_list_is_shown_as_a_count(self, tmp_path: Path) -> None:
        """Positive unit test for render_fields(). It contains the following steps:
        - render a section whose hd_names= holds three devices
        - ASSERT: the value cell shows the number of devices, not the first path
        """
        model = _model(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/a\n\t/dev/b\n\t/dev/c\n")
        views = model.fields_of(_row(model, "HD"))
        lines = panes.render_fields(views, 0, 0, panes.layout_for(80, 24))
        assert any("3 devices..." in line for line in lines)


class _FakeWindow:
    """A curses window that records what it is asked to do, for the drawing tests."""

    def __init__(self, height: int = 24, width: int = 80) -> None:
        self.height = height
        self.width = width
        self.calls: list = []
        self.children: list = []

    def getmaxyx(self):
        return self.height, self.width

    def derwin(self, height, width, top, left):
        child = _FakeWindow(height, width)
        self.children.append(child)
        self.calls.append(("derwin", height, width, top, left))
        return child

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name,) + args)
        return record

class TestEditorApp:
    """Unit test class for the key dispatch of the smfc.config_editor.app module."""

    def test_tab_moves_between_the_panes(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.handle_key(). It contains the following steps:
        - press Tab twice
        - ASSERT: the cursor moves to the parameter list and back
        """
        app = EditorApp(_model(tmp_path))
        assert app.pane is PANE_SECTIONS
        app.handle_key(ord("\t"))
        assert app.pane is PANE_FIELDS
        app.handle_key(ord("\t"))
        assert app.pane is PANE_SECTIONS

    def test_the_cursor_skips_the_separator(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.move_row(). It contains the following steps:
        - move the cursor down to the end of the section list
        - ASSERT: it never stops on the separator line
        - ASSERT: it stops at the Overview row and does not run past the end
        """
        app = EditorApp(_model(tmp_path))
        for _ in range(len(app.model.rows) + 5):
            app.handle_key(curses.KEY_DOWN)
        assert app.row.kind is RowKind.OVERVIEW
        for _ in range(len(app.model.rows) + 5):
            app.handle_key(curses.KEY_UP)
        assert app.row_index == 0

    def test_typing_a_value_writes_it(self, tmp_path: Path) -> None:
        """Positive unit test for the editing keys. It contains the following steps:
        - move to the [CPU] row and into the parameter list, and open min_temp for editing
        - type a new value and press Enter
        - ASSERT: the value is written into the file
        - ASSERT: the unsaved-changes flag is set
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "min_temp"][0]
        app.handle_key(curses.KEY_ENTER)
        assert app.editing.text == "30.0"
        for _ in range(4):
            app.handle_key(curses.KEY_BACKSPACE)
        for char in "42.5":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert app.editing is None
        assert app.model.writer.get("CPU", "min_temp") == "42.5"
        assert app.model.dirty is True

    def test_escape_drops_the_typed_value(self, tmp_path: Path) -> None:
        """Negative unit test for the editing keys. It contains the following steps:
        - open a parameter for editing, type into it, and press Esc
        - ASSERT: the file still holds the old value
        - ASSERT: the file is not marked as changed
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "min_temp"][0]
        app.handle_key(curses.KEY_ENTER)
        app.handle_key(ord("9"))
        app.handle_key(27)
        assert app.model.writer.get("CPU", "min_temp") == "30.0"
        assert app.model.dirty is False

    def test_space_toggles_a_family(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.toggle(). It contains the following steps:
        - put the cursor on the [CPU] row and press Space
        - ASSERT: the family is switched off
        - ASSERT: the message says what happened
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.handle_key(ord(" "))
        assert app.model.writer.get("CPU", "enabled") == "0"
        assert "disabled" in app.message

    def test_a_read_only_file_refuses_every_change(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp. It contains the following steps:
        - mark the model read-only, then press Space and try to edit a parameter
        - ASSERT: nothing is changed
        - ASSERT: both messages name the way to fix it
        """
        app = EditorApp(_model(tmp_path))
        app.model.read_only = True
        app.handle_key(ord(" "))
        assert "sudo smfc-config" in app.message
        app.pane = PANE_FIELDS
        app.start_edit()
        assert app.editing is None
        assert "sudo smfc-config" in app.message

    def test_a_path_opens_the_wide_input_popup(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.start_edit(). It contains the following steps:
        - open a path parameter, which is too long for the value cell
        - ASSERT: no in-place edit starts
        - ASSERT: a text popup opens, holding the current value
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "Ipmi"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "command"][0]
        app.start_edit()
        assert app.editing is None
        assert isinstance(app.popup, popups.TextPopup)
        assert app.popup.text == "/usr/bin/ipmitool"

    def test_escape_does_not_quit_the_editor(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp.handle_key(). It contains the following steps:
        - move the cursor into the parameter list and press Esc
        - ASSERT: the editor is still running, because Esc is the first byte of every function key
          sequence and a terminal that delivers them byte by byte would otherwise close it on F2
        - ASSERT: the cursor returns to the section list instead
        """
        app = EditorApp(_model(tmp_path))
        app.pane = PANE_FIELDS
        app.handle_key(27)
        assert app.running is True
        assert app.pane is PANE_SECTIONS

    def test_an_invalid_value_is_marked_and_explained(self, tmp_path: Path) -> None:
        """Positive unit test for the per-field validation. It contains the following steps:
        - load a file whose min_temp is not a number and whose steps is below its minimum
        - ASSERT: both are marked invalid, so the pane paints them red
        - ASSERT: each carries the reason, which the help pane shows in place of the range line
        - ASSERT: a parameter that is absent is never invalid, because its default is used
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nmin_temp=abc\nsteps=0\n")
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["min_temp"].state is FieldState.INVALID
        assert views["min_temp"].reason == "a number is needed"
        assert views["steps"].state is FieldState.INVALID
        assert views["max_temp"].state is FieldState.NORMAL

    @pytest.mark.parametrize(
        "written, shown",
        [
            pytest.param("1", "yes", id="one"),
            pytest.param("0", "no", id="zero"),
            pytest.param("true", "yes", id="true"),
            pytest.param("false", "no", id="false"),
            pytest.param("on", "yes", id="on"),
            pytest.param("off", "no", id="off"),
        ],
    )
    def test_a_boolean_is_shown_in_words(self, tmp_path: Path, written: str, shown: str) -> None:
        """Positive unit test for the boolean rendering. It contains the following steps:
        - write each form the parser accepts into a boolean parameter
        - ASSERT: the value cell reads yes or no, whichever form the file holds
        """
        model = _model(tmp_path, f"[Ipmi]\n[CPU]\nenabled={written}\n")
        views = model.fields_of(_row(model, "CPU"))
        lines = panes.render_fields(views, 0, 0, panes.layout_for(80, 24))
        assert lines[0].split()[-1] == shown

    def test_enter_switches_a_boolean(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.start_edit(). It contains the following steps:
        - press Enter on a boolean parameter twice
        - ASSERT: no text edit opens, because a boolean has two values rather than free text
        - ASSERT: the file carries 1 and then 0, the form every shipped sample uses
        - ASSERT: the message names the state in words
        """
        app = EditorApp(_model(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/a\n"
                                         "standby_guard_enabled=0\n"))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "HD"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views())
                           if v.key == "standby_guard_enabled"][0]
        app.start_edit()
        assert app.editing is None and app.popup is None
        assert app.model.writer.get("HD", "standby_guard_enabled") == "1"
        assert app.message.endswith("yes")
        app.start_edit()
        assert app.model.writer.get("HD", "standby_guard_enabled") == "0"
        assert app.message.endswith("no")

    def test_the_help_of_a_boolean_says_yes_or_no(self, tmp_path: Path) -> None:
        """Positive unit test for Field.range_text(). It contains the following steps:
        - read the range line of a boolean parameter
        - ASSERT: it names the two words, not a type and a number
        """
        model = _model(tmp_path)
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["enabled"].field.range_text() == "yes or no, default no"

    def test_an_enum_opens_the_choice_popup_and_writes_the_choice(self, tmp_path: Path) -> None:
        """Positive unit test for the choice popup. It contains the following steps:
        - open temp_calc, which accepts three values
        - move to another value and accept it
        - ASSERT: the popup closes and the value is written into the file
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "temp_calc"][0]
        app.start_edit()
        assert isinstance(app.popup, popups.ChoicePopup)
        app.handle_key(curses.KEY_DOWN)
        app.handle_key(10)
        assert app.popup is None
        assert app.model.writer.get("CPU", "temp_calc") == "2"

    def test_a_refused_value_leaves_the_file_alone(self, tmp_path: Path) -> None:
        """Negative unit test for the text popup. It contains the following steps:
        - open the curve of a section and type a value with only one point in it
        - press Enter
        - ASSERT: the popup stays open, because the parser would reject that value
        - ASSERT: nothing was written
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "control_function"][0]
        app.start_edit()
        for char in "30-35":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert app.popup is not None and app.popup.error
        assert app.model.writer.get("CPU", "control_function") is None

    def test_a_value_accepted_in_a_popup_reaches_the_file(self, tmp_path: Path) -> None:
        """Positive unit test for the text popup. It contains the following steps:
        - open the curve of a section, type a value the parser accepts, and press Enter
        - ASSERT: the popup closes
        - ASSERT: the value is written into the file and parses back as two points
        - ASSERT: the four parameters the curve overrides become inactive
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "control_function"][0]
        app.start_edit()
        for char in "30-35, 60-100":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert app.popup is None
        assert app.model.writer.get("CPU", "control_function") == "30-35, 60-100"
        views = {v.key: v for v in app.views()}
        assert views["min_temp"].state is FieldState.INACTIVE

    def test_adding_an_instance_through_the_dialog(self, tmp_path: Path) -> None:
        """Positive unit test for the instance dialog. It contains the following steps:
        - open the add dialog, accept the first family and the first free zone
        - ASSERT: a numbered instance is written, enabled, on a zone no other instance claims
        - ASSERT: the cursor moves to the new row
        """
        app = EditorApp(_model(tmp_path))
        app.add_instance()
        assert isinstance(app.popup, popups.InstancePopup)
        app.handle_key(10)
        assert app.popup is None
        assert app.model.writer.get("CPU:1", "ipmi_zone") == "1"
        assert app.row.name == "CPU:1"

    def test_removing_an_instance_asks_first(self, tmp_path: Path) -> None:
        """Positive unit test for the remove dialog. It contains the following steps:
        - add an instance, put the cursor on it and ask to remove it
        - answer no, then ask again and answer yes
        - ASSERT: no leaves the instance in the file
        - ASSERT: yes removes it
        - ASSERT: the base section cannot be removed this way
        """
        app = EditorApp(_model(tmp_path))
        app.model.add_instance("CPU")
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU:1"][0]
        app.remove_instance()
        app.handle_key(ord("n"))
        assert app.model.writer.has_section("CPU:1") is True
        app.remove_instance()
        app.handle_key(ord("y"))
        assert app.model.writer.has_section("CPU:1") is False
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.remove_instance()
        assert app.popup is None
        assert "numbered instance" in app.message

    def test_a_device_typed_by_hand_reaches_the_file(self, tmp_path: Path) -> None:
        """Positive unit test for the add-by-path key. It contains the following steps:
        - open the device selector of hd_names and press p
        - type a by-id path and accept it
        - ASSERT: the selector comes back with the device ticked
        - accept the selector
        - ASSERT: the path is written into the file and parses back
        """
        app = EditorApp(_model(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=\n"))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "HD"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "hd_names"][0]
        app.start_edit()
        assert isinstance(app.popup, popups.DevicePopup)
        app.handle_key(ord("p"))
        assert isinstance(app.popup, popups.TextPopup)
        for char in "ata-TYPED":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert isinstance(app.popup, popups.DevicePopup)
        app.handle_key(10)
        assert app.popup is None
        assert app.model.writer.get("HD", "hd_names") == "/dev/disk/by-id/ata-TYPED"

    def test_a_typed_path_must_be_a_by_id_path(self, tmp_path: Path) -> None:
        """Negative unit test for the add-by-path key. It contains the following steps:
        - open the selector, press p, and clear the prefix it offers
        - type a kernel name and press Enter
        - ASSERT: the popup refuses it, because a kernel name changes across boots
        """
        app = EditorApp(_model(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=\n"))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "HD"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "hd_names"][0]
        app.start_edit()
        app.handle_key(ord("p"))
        for _ in range(20):
            app.handle_key(curses.KEY_BACKSPACE)
        for char in "/dev/sda":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert app.popup.error

    def test_a_terminal_that_goes_away_stops_the_editor(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp.handle_key(). It contains the following steps:
        - deliver the value curses returns when there is no input to read
        - ASSERT: the editor stops
        - ASSERT: it stops even while a popup is open, because the terminal is gone either way
        A terminal that closes makes getch() answer at once instead of waiting. Ignoring that answer
        spins on one core for as long as the process lives, which is what happened during testing:
        an editor left behind by a closed pseudo-terminal ran for five hours at 25 percent of a CPU.
        """
        app = EditorApp(_model(tmp_path))
        app.handle_key(-1)
        assert app.running is False
        app = EditorApp(_model(tmp_path))
        app.popup = popups.ConfirmPopup(title="x", question="y?")
        app.handle_key(-1)
        assert app.running is False

    def test_f5_runs_the_checks_and_f10_quits(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.handle_key(). It contains the following steps:
        - press F5, then F10
        - ASSERT: the checks have run
        - ASSERT: the loop is asked to stop
        """
        app = EditorApp(_model(tmp_path))
        assert app.model.checked is False
        app.handle_key(curses.KEY_F5)
        assert app.model.checked is True
        app.handle_key(curses.KEY_F10)
        assert app.running is False

    def test_a_popup_erases_the_panes_under_it(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp._draw_popup(). It contains the following steps:
        - open the popup of a parameter and draw it on a window that records every call
        - ASSERT: the window of the popup is erased before anything is drawn in it
        A window made with derwin() shares the memory of the screen, and bkgd() only sets the
        background attribute. Without the erase the popup fills with pieces of the panes behind it.
        """
        app = EditorApp(_model(tmp_path), colour=False)
        app.row_index = next(i for i, r in enumerate(app.model.rows) if r.name == "CPU")
        app.pane = PANE_FIELDS
        app.field_index = next(i for i, v in enumerate(app.views()) if v.key == "control_function")
        app.start_edit()
        assert app.popup is not None
        screen = _FakeWindow()
        app._draw_popup(screen, panes.layout_for(80, 24))        # pylint: disable=protected-access
        window = screen.children[0]
        names = [call[0] for call in window.calls]
        assert "erase" in names
        assert names.index("erase") < names.index("box")

    def test_the_cursor_follows_the_text_being_typed(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp drawing. It contains the following steps:
        - type into a value edited in the parameter pane and draw that pane
        - ASSERT: a cursor position is recorded, so the terminal cursor is shown while typing
        - open a value edited in a popup and draw the popup
        - ASSERT: a cursor position is recorded there too
        - close the popup and draw again
        - ASSERT: no position is recorded, so the cursor is hidden when nothing is being typed
        A user typing needs to see where the next character lands; the cursor is the only mark of it.
        """
        app = EditorApp(_model(tmp_path), colour=False)
        app.row_index = next(i for i, r in enumerate(app.model.rows) if r.name == "CPU")
        app.pane = PANE_FIELDS
        layout = panes.layout_for(80, 24)
        views = app.views()

        app.field_index = next(i for i, v in enumerate(views) if v.key == "polling")
        app.start_edit()
        app.handle_key(ord("9"))
        lines = panes.render_fields(views, app.field_index, app.field_top, layout, app.editing)
        app._draw_field_lines(_FakeWindow(), layout, lines, 1)   # pylint: disable=protected-access
        assert app.cursor_at is not None
        app.finish_edit(False)

        app.field_index = next(i for i, v in enumerate(views) if v.key == "control_function")
        app.start_edit()
        app.cursor_at = None
        app._draw_popup(_FakeWindow(), layout)                   # pylint: disable=protected-access
        assert app.cursor_at is not None

        app.popup = None
        app.cursor_at = None
        app._draw_field_lines(_FakeWindow(), layout, lines, 1)   # pylint: disable=protected-access
        assert app.cursor_at is None

    def test_f5_runs_the_hardware_probes(self, tmp_path: Path, mocker) -> None:
        """Positive unit test for EditorApp.check(). It contains the following steps:
        - press F5 with the probes mocked
        - ASSERT: the probes are run, which is what the key promises
        - ASSERT: the message says how many findings there are
        """
        probe = mocker.patch("smfc.config_editor.model.probe_all", return_value=[])
        mocker.patch("smfc.config_editor.model.loaded_modules", return_value=NO_MODULES)
        app = EditorApp(_model(tmp_path))
        app.handle_key(curses.KEY_F5)
        probe.assert_called_once()
        assert "findings" in app.message

    def test_saving_an_invalid_file_is_allowed_and_says_so(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.save(). It contains the following steps:
        - open the shipped configuration file, which the parser rejects, and press F2
        - ASSERT: the file is written, because nothing blocks a save
        - ASSERT: the message says smfc will not start and that the running service is untouched
        """
        app = EditorApp(_shipped(tmp_path))
        app.handle_key(curses.KEY_F2)
        assert app.model.dirty is False
        assert "will not start" in app.message
        assert "running service" in app.message


class TestPopups:
    """Unit test class for the smfc.config_editor.popups module."""

    def test_a_value_the_parser_refuses_keeps_the_popup_open(self) -> None:
        """Negative unit test for TextPopup. It contains the following steps:
        - open a text popup whose validator refuses a value
        - type the bad value and press Enter
        - ASSERT: the popup stays open, so the user can correct it
        - ASSERT: it says what is wrong
        - ASSERT: Esc closes it anyway, so nobody is trapped
        """
        popup = popups.TextPopup(title="min_temp", text="", validator=lambda t: "a number is needed")
        for char in "abc":
            popup.handle_key(ord(char))
        popup.handle_key(10)
        assert popup.done is False
        assert popup.error == "a number is needed"
        popup.handle_key(27)
        assert popup.done is True and popup.accepted is False and popup.value() is None

    def test_a_good_value_closes_the_popup(self) -> None:
        """Positive unit test for TextPopup. It contains the following steps:
        - type a value the validator accepts and press Enter
        - ASSERT: the popup closes and hands the value back, stripped
        """
        popup = popups.TextPopup(title="command", text="", validator=lambda t: "")
        for char in " /usr/bin/ipmitool ":
            popup.handle_key(ord(char))
        popup.handle_key(10)
        assert popup.accepted is True
        assert popup.value() == "/usr/bin/ipmitool"

    def test_backspace_clears_the_error(self) -> None:
        """Positive unit test for TextPopup. It contains the following steps:
        - refuse a value, then press backspace
        - ASSERT: the message goes away, because the value is being corrected
        """
        popup = popups.TextPopup(title="x", text="ab", validator=lambda t: "no")
        popup.handle_key(10)
        assert popup.error
        popup.handle_key(curses.KEY_BACKSPACE)
        assert popup.error == ""

    def test_the_choice_popup_starts_on_the_current_value(self) -> None:
        """Positive unit test for ChoicePopup. It contains the following steps:
        - open a choice popup on the second of three values
        - move down and accept
        - ASSERT: the value it returns is the one the cursor is on
        """
        popup = popups.ChoicePopup(title="temp_calc", choices=["0", "1", "2"],
                                   labels=["minimum", "average", "maximum"], index=1)
        popup.handle_key(curses.KEY_DOWN)
        popup.handle_key(10)
        assert popup.value() == "2"

    def test_the_device_popup_ticks_and_returns_sorted_paths(self) -> None:
        """Positive unit test for DevicePopup. It contains the following steps:
        - open the selector with three devices, one of them already listed
        - tick a second one and accept
        - ASSERT: both ticked devices are returned, sorted as the file holds them
        """
        entries = [popups.DeviceEntry(path="/dev/disk/by-id/ata-C", label="C"),
                   popups.DeviceEntry(path="/dev/disk/by-id/ata-A", label="A", ticked=True),
                   popups.DeviceEntry(path="/dev/disk/by-id/ata-B", label="B")]
        popup = popups.DevicePopup(title="hd_names", entries=entries)
        popup.handle_key(ord(" "))
        popup.handle_key(10)
        assert popup.value() == ["/dev/disk/by-id/ata-A", "/dev/disk/by-id/ata-C"]

    def test_all_and_none_keys(self) -> None:
        """Positive unit test for DevicePopup. It contains the following steps:
        - press a, then n
        - ASSERT: a ticks every device and n unticks every one
        """
        entries = [popups.DeviceEntry(path="/dev/a", label="a"),
                   popups.DeviceEntry(path="/dev/b", label="b")]
        popup = popups.DevicePopup(title="hd_names", entries=entries)
        popup.handle_key(ord("a"))
        assert all(e.ticked for e in entries)
        popup.handle_key(ord("n"))
        assert not any(e.ticked for e in entries)

    def test_a_device_typed_by_hand_is_kept_and_marked(self) -> None:
        """Positive unit test for DevicePopup.add_path(). It contains the following steps:
        - add a device the machine does not have
        - ASSERT: it is listed, ticked, and marked missing
        - ASSERT: adding it twice does not list it twice
        """
        popup = popups.DevicePopup(title="hd_names", entries=[])
        popup.add_path("/dev/disk/by-id/ata-NEW")
        popup.add_path("/dev/disk/by-id/ata-NEW")
        assert len(popup.entries) == 1
        assert popup.entries[0].ticked is True
        assert popup.entries[0].present is False
        assert "(missing)" in popup.entries[0].label

    def test_the_confirm_popup_answers_yes_or_no(self) -> None:
        """Positive unit test for ConfirmPopup. It contains the following steps:
        - answer the question with n, then with y on a second popup
        - ASSERT: n and Esc both mean no, and y means yes
        """
        popup = popups.ConfirmPopup(title="remove", question="Remove [CPU:1]?")
        popup.handle_key(ord("n"))
        assert popup.done is True and popup.value() is False
        popup = popups.ConfirmPopup(title="remove", question="Remove [CPU:1]?")
        popup.handle_key(ord("y"))
        assert popup.value() is True

    def test_the_instance_popup_offers_only_free_zones(self) -> None:
        """Positive unit test for InstancePopup. It contains the following steps:
        - open the dialog with two families, where the second one has no free zone
        - move to that family and press Enter
        - ASSERT: it refuses and says why, instead of writing a section the parser would reject
        - ASSERT: the first family, which has a free zone, is accepted
        """
        free = {"CPU": [2, 3], "HD": []}
        popup = popups.InstancePopup(title="add", families=["CPU", "HD"], zones=free["CPU"],
                                     on_family=free.get)
        popup.handle_key(curses.KEY_DOWN)
        popup.handle_key(10)
        assert popup.done is False
        assert "zone" in popup.error
        popup.handle_key(curses.KEY_UP)
        popup.handle_key(curses.KEY_RIGHT)
        popup.handle_key(10)
        assert popup.value() == ("CPU", 3)


class TestCommand:
    """Unit test class for the smfc.config_editor.cmd module."""

    def test_a_missing_file_names_the_template_of_the_installed_release(self, tmp_path: Path,
                                                                       capsys) -> None:
        """Negative unit test for main(). It contains the following steps:
        - run smfc-config against a path that does not exist, with no backup beside it
        - ASSERT: it exits with the configuration error code of the service
        - ASSERT: it names the tagged URL of the template, so the version always matches the daemon
        """
        assert main(["-c", str(tmp_path / "nosuch.conf")]) == EXIT_CONFIG_ERROR
        err = capsys.readouterr().err
        assert "does not exist" in err
        assert "refs/tags/v" in err

    def test_a_missing_file_offers_the_local_backup_first(self, tmp_path: Path, capsys) -> None:
        """Negative unit test for main(). It contains the following steps:
        - put a backup beside a configuration file that does not exist
        - run smfc-config against it
        - ASSERT: the backup is named, and the copy command is printed
        - ASSERT: the download is not offered, because a local file is the better answer
        """
        target = tmp_path / "smfc.conf"
        (tmp_path / "smfc.conf.20260914_120000").write_text(SMALL, encoding="utf-8")
        assert main(["-c", str(target)]) == EXIT_CONFIG_ERROR
        err = capsys.readouterr().err
        assert "smfc.conf.20260914_120000" in err
        assert "refs/tags/v" not in err

class TestLineEdit:
    """Unit test class for the smfc.config_editor.lineedit module."""

    def test_a_value_opens_with_the_caret_at_its_end(self) -> None:
        """Positive unit test for LineEdit.of(). It contains the following steps:
        - open a value that the file holds
        - ASSERT: the text is the value, unchanged
        - ASSERT: the caret is at its end, so typing continues the value instead of replacing it
        - ASSERT: the field starts in insert mode, which is what a terminal editor does
        """
        line = LineEdit.of("30.0")
        assert line.text == "30.0"
        assert line.caret == 4
        assert line.insert is True

    def test_insert_pushes_the_text_along(self) -> None:
        """Positive unit test for LineEdit.handle_key(). It contains the following steps:
        - move the caret to the start of a value and type a character
        - ASSERT: the character is inserted and nothing is lost
        - ASSERT: the caret moved past what was typed
        """
        line = LineEdit.of("45")
        line.handle_key(curses.KEY_HOME)
        line.handle_key(ord("1"))
        assert line.text == "145"
        assert line.caret == 1

    def test_overwrite_types_over_the_text(self) -> None:
        """Positive unit test for LineEdit.handle_key(). It contains the following steps:
        - switch the field to overwrite with the Insert key and type at the start
        - ASSERT: the character under the caret is replaced, so the value does not grow
        - ASSERT: typing at the end still appends, because there is nothing there to replace
        """
        line = LineEdit.of("45")
        line.handle_key(curses.KEY_HOME)
        line.handle_key(curses.KEY_IC)
        assert line.insert is False
        line.handle_key(ord("9"))
        assert line.text == "95"
        line.handle_key(curses.KEY_END)
        line.handle_key(ord("7"))
        assert line.text == "957"

    def test_the_caret_keys_move_without_changing_the_text(self) -> None:
        """Positive unit test for LineEdit.handle_key(). It contains the following steps:
        - move left, right, home and end over a value
        - ASSERT: the caret never leaves the text
        - ASSERT: the text is untouched
        """
        line = LineEdit.of("abc")
        for _ in range(5):
            line.handle_key(curses.KEY_LEFT)
        assert line.caret == 0
        for _ in range(5):
            line.handle_key(curses.KEY_RIGHT)
        assert line.caret == 3
        line.handle_key(curses.KEY_HOME)
        assert line.caret == 0
        line.handle_key(curses.KEY_END)
        assert line.caret == 3
        assert line.text == "abc"

    def test_backspace_and_delete_take_the_right_character(self) -> None:
        """Positive unit test for LineEdit.handle_key(). It contains the following steps:
        - put the caret in the middle of a value, then press backspace and delete
        - ASSERT: backspace removes the character before the caret and moves it back
        - ASSERT: delete removes the character under the caret and leaves it where it was
        - ASSERT: backspace at the start of the value does nothing
        """
        line = LineEdit(text="abcd", caret=2)
        line.handle_key(curses.KEY_BACKSPACE)
        assert line.text == "acd" and line.caret == 1
        line.handle_key(curses.KEY_DC)
        assert line.text == "ad" and line.caret == 1
        line.handle_key(curses.KEY_HOME)
        line.handle_key(curses.KEY_BACKSPACE)
        assert line.text == "ad" and line.caret == 0

    def test_a_key_it_does_not_know_is_handed_back(self) -> None:
        """Negative unit test for LineEdit.handle_key(). It contains the following steps:
        - press a key the field has no use for
        - ASSERT: it reports the key as unused, so the caller can act on it
        """
        line = LineEdit.of("x")
        assert line.handle_key(curses.KEY_F5) is False
        assert line.handle_key(ord("y")) is True

    def test_a_value_longer_than_its_field_follows_the_caret(self) -> None:
        """Positive unit test for LineEdit.view(). It contains the following steps:
        - open a value longer than the field it is drawn in
        - ASSERT: the end of the value is shown, because that is where the caret is
        - ASSERT: the caret stays inside the field
        - move to the start of the value
        - ASSERT: the beginning is shown instead
        - ASSERT: a value shorter than the field is padded to it, so the field keeps its width
        """
        line = LineEdit.of("30-35, 50-55, 65-100")
        text, caret = line.view(10)
        assert text == "5, 65-100 "
        assert caret == 9
        line.handle_key(curses.KEY_HOME)
        text, caret = line.view(10)
        assert text == "30-35, 50-"
        assert caret == 0
        short, caret = LineEdit.of("ab").view(10)
        assert short == "ab" + " " * 8
        assert caret == 2


# End.
