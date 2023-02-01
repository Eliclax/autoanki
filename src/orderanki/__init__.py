from aqt import mw, gui_hooks, AnkiQt
from aqt.utils import qconnect, tooltip, showWarning, showInfo
from aqt.qt import *
from anki.notes import NoteId, Note
from anki.models import NotetypeDict, NotetypeId, ModelManager
from aqt.fields import *

from typing import Sequence, Optional, Set, Union, List, Tuple

class OrderByFieldDialog(QDialog):
    """
    The class for the Order by Field dialog.
    """

    def __init__(self, browser: QMainWindow, nids : Sequence[NoteId]) -> None:
        """
        Initialise the pop-up window for ordering by field.

        :param browser: A QMainWindow object for the browser
        :param nids: A Sequence[NoteId] for ordering
        """

        QDialog.__init__(self, parent=browser)
        self.browser: QMainWindow = browser
        self.nids = nids
        self.nid = self.nids[0]
        self.bmw: AnkiQt = self.browser.mw
        note: Note = self.bmw.col.get_note(self.nid)
        self.model: Optional[NotetypeDict] = note.note_type()
        self.fields = self.bmw.col.models.field_names(self.model)
        self._setup_ui()
        self.currentIdx: Optional[int] = None

    def _setup_ui(self) -> None:
        """
        Sets up the UI for the Order by Field dialog.
        """

        ui_main_vbox = QVBoxLayout()
        if True:
            ui_desc = QLabel("Order \"new\" cards by some field.")
            ui_desc.setWordWrap(True)

            ui_selno = QLabel("<b>Notes selected:</b> " + str(len(self.nids)))

            ui_form = QFormLayout()
            if True:

                self.ui_field_selector = QComboBox()
                self.ui_field_selector.addItems(self.fields)

                self.ui_positioning_selector = QComboBox()
                self.ui_positioning_selector.addItems(["Keep in place", "Newest", "Oldest"])

            ui_form.addRow(QLabel("Field:"), self.ui_field_selector)
            ui_form.addRow(QLabel("Positioning:"), self.ui_positioning_selector)

            # ui_asc_desc_QHBoxLayout = QHBoxLayout()
            # self.ui_asc_desc_QButtonGroup = QButtonGroup()
            # if True:
            #     self.ui_asc_QRadioButton = QRadioButton("Sort &ascending")
            #     self.ui_asc_QRadioButton.toggle()
            #     self.ui_desc_QRadioButton = QRadioButton("Sort &descending")
            # self.ui_asc_desc_QButtonGroup.addButton(self.ui_asc_QRadioButton)
            # self.ui_asc_desc_QButtonGroup.addButton(self.ui_desc_QRadioButton)
            # ui_asc_desc_QHBoxLayout.addWidget(self.ui_asc_QRadioButton)
            # ui_asc_desc_QHBoxLayout.addWidget(self.ui_desc_QRadioButton)

            # ui_str_int_QHBoxLayout = QHBoxLayout()
            # self.ui_str_int_QButtonGroup = QButtonGroup()
            # if True:
            #     self.ui_str_QRadioButton = QRadioButton("String")
            #     self.ui_str_QRadioButton.toggle()
            #     self.ui_int_QRadioButton = QRadioButton("Number")
            # self.ui_str_int_QButtonGroup.addButton(self.ui_str_QRadioButton)
            # self.ui_str_int_QButtonGroup.addButton(self.ui_int_QRadioButton)
            # ui_str_int_QHBoxLayout.addWidget(self.ui_str_QRadioButton)
            # ui_str_int_QHBoxLayout.addWidget(self.ui_int_QRadioButton)

            self.ui_sort_desc_QCheckBox = QCheckBox("Sort &descending")
            self.ui_field_nums_QCheckBox = QCheckBox("Field contains &numbers")
            self.ui_forget_cards_QCheckBox = QCheckBox("&Forget learnt cards")

            ui_button_box = QDialogButtonBox(Qt.Horizontal, self)
            if True:
                ui_done_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Ok)
                ui_cancel_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
                ui_help_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Help)
                ui_done_button.setToolTip("Begin ordering...")
                ui_done_button.clicked.connect(self.accept)
                ui_cancel_button.clicked.connect(self.reject)

        ui_main_vbox.addLayout(ui_form)
        ui_main_vbox.addWidget(self.ui_sort_desc_QCheckBox)
        ui_main_vbox.addWidget(self.ui_field_nums_QCheckBox)
        ui_main_vbox.addWidget(self.ui_forget_cards_QCheckBox)
        ui_main_vbox.addWidget(ui_button_box)

        self.setLayout(ui_main_vbox)
        self.ui_field_selector.setFocus()
        self.setWindowTitle("Order by Field")

def order_by_field(browser) -> None:
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    dialog = OrderByFieldDialog(browser, nids)
    dialog.exec_()

def setup_menu(browser : QMainWindow) -> None:
    menu = browser.form.menu_Notes
    menu.addSeparator()

    # Set up a new menu item, "Order by field"
    order_by_field_action = QAction("Order by field...", mw)
    menu.addAction(order_by_field_action)
    qconnect(order_by_field_action.triggered, lambda: order_by_field(browser))

gui_hooks.browser_menus_did_init.append(setup_menu)