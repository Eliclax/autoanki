from math import ceil
from aqt import mw, gui_hooks, AnkiQt
from aqt.utils import qconnect, tooltip, showWarning, showInfo
from aqt.qt import *
from anki.notes import NoteId, Note
from anki.models import NotetypeDict, NotetypeId, ModelManager
from aqt.fields import *

from time import sleep
import re
from typing import Sequence, Optional, Set, Union, List, Tuple

from . import wiki
from urllib import error
import concurrent.futures
import queue
import time
import requests

class AddFameDialog(QDialog):
    """
    The class for the Add Fame dialog.
    """

    def __init__(self, browser: QMainWindow, nids : Sequence[NoteId]) -> None:
        """
        Initialise the pop-up window for Adding Fame.

        :param browser: A QMainWindow object for the browser
        :param nids: A Sequence[NoteId] object for adding fame to
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
        if len(self.nids) == 1:
            msg = "<b>Adding Wikipedia fame to a single note</b><br><br>You have selected a single note."
            msg+= "Due to a weird bug I can't figure out, adding "
            msg+= "Wikipedia fame data when selecting a single note will result in incomplete data. "
            msg+= "This shouldn't pose any risk of messing up your deck, though."
            showWarning(msg,parent=self,textFormat="rich")
        self.currentIdx: Optional[int] = None

    def _handle_network_error(self, err: Exception, msg: str = "") -> None:
        if isinstance(err, requests.HTTPError):
            txt = str(err.code) + " HTTP ERROR"
        else:
            txt = tr.addons_please_check_your_internet_connection() + "\n\nError: " + str(err.reason)
        showWarning(msg + "\n\n" + txt, textFormat="rich", parent=self)

    def _merge_field_into_tag(self, merge_string: str, note: Note) -> str:
        """
        Merge the tags from a given Note into a merge String.

        :param merge_string:  The string containing merge tags
        :param note:  The note
        """

        merge_result = ""
        merge_re = r"\{\{[^\{].*?\}\}"
        se = re.search(merge_re, merge_string)
        while se is not None:
            field_name = se.group()[2:-2]
            # note = mw.col.get_note(self.nid)
            note_values = [item for item in note.items() if item[0] == field_name]
            if len(note_values) >= 1:
                merge_result += merge_string[0:se.span()[0]] + str(note_values[0][1])
            else:
                merge_result += merge_string[0:se.span()[1]]
            merge_string = merge_string[se.span()[1]:]
            se = re.search(merge_re, merge_string)
        merge_result += merge_string
        return merge_result

    def _get_fields(self) -> List[str]:
        """
        Returns a list of field names for the model that the notes are based on.

        :return: A list of field names for the notes' model
        """

        return self.bmw.col.models.field_names(self.model)

    # See https://github.com/ankitects/anki/blob/d110c4916cf1d83fbeae48ae891515c79a412018/qt/aqt/fields.py#L142
    def _unique_name(self, txt: str, ignoreOrd: Optional[int] = None) -> Optional[str]:
        """
        Deals with the newly created fields having a unique name.
        """

        if not txt:
            return None
        if txt[0] in "#^/":
            showWarning(tr.fields_name_first_letter_not_valid())
            return None
        for letter in """:{"}""":
            if letter in txt:
                showWarning(tr.fields_name_invalid_letter())
                return None
        for f in self.model["flds"]:
            if ignoreOrd is not None and f["ord"] == ignoreOrd:
                continue
            if f["name"] == txt:
                showWarning(tr.fields_that_field_name_is_already_used())
                return None
        return txt

    # See https://github.com/ankitects/anki/blob/d110c4916cf1d83fbeae48ae891515c79a412018/qt/aqt/fields.py#L179
    def accept(self) -> None:
        """
        When the OK button in the Dialog is clicked, start adding the Fame.
        """

        # Make the new Wiki field
        def _add_field(field_name: str) -> None:
            """
            Add a field to the model called field_name.

            :param field_name: The name of the field to add.
            """

            self.mm = ModelManager(self.bmw.col)
            self.change_tracker = ChangeTracker(self.bmw)
            self.currentIdx = len(self.model["flds"])
            field_name = self._unique_name(field_name)
            if not field_name:
                return
            if not self.change_tracker.mark_schema():
                return
            f = self.mm.new_field(field_name)
            self.mm.add_field(self.model, f)

            def on_done(changes: OpChanges) -> None:
                # tooltip("New field \"" + self.wfd_ui_dict["new_field_name_editor"].text() + "\" added.", parent=self.parentWidget())
                QDialog.accept(self)

            update_notetype_legacy(parent=self.bmw, notetype=self.model).success(on_done).run_in_background()
            sleep(0.2) # The previous command requires time to propagate its changes

        # Check if we have a connection to Wikipedia.
        try:
            wiki.search_article_url("Noodles")
        except error.URLError as err:
            self._handle_network_error(err)
            return

        # Proper English phrasing for fields
        def fields_listing(fields: List[str]) -> str:
            if len(fields) == 0: return ""
            if len(fields) == 1: return f"field \"{fields[0]}\""
            if len(fields) == 2: return f"fields \"{fields[0]}\" and \"{fields[1]}\""
            if len(fields) >= 3: return "fields \"" + "\", \"".join(fields[0:-1]) + f"\", and \"{fields[-1]}\""

        # Add necessary fields
        fn = self.wfd_ui_dict["new_field_name_editor"].text()
        field_names_new: Dict[str, str] = {"pageviews": fn, "article": fn+" (URL)", "desc": fn + " (Description)"}
        field_names_old: List[str] = self._get_fields()
        fields_added: List[str] = []
        fields_reused: List[str] = []
        for code in field_names_new:
            if field_names_new[code] not in field_names_old:
                fields_added.append(field_names_new[code])
            else:
                fields_reused.append(field_names_new[code])

        if fields_reused:
            text = f"The {fields_listing(fields_reused)} will be overwritten.  Continue?"
            if not askUser(text,parent=self.parentWidget()):
                return None

        for field_added in fields_added:
            _add_field(field_added)

        CONNECTIONS = 100               # Number of workers to use for the threads
        RATE = 100                      # Ratelimit of RATE per PER seconds
        PER = 1                         # Ratelimit of RATE per PER seconds
        TIMEOUT = 5                     # Amount of time to wait for an http request
        MAX_TITLES = 50                 # Maximum number of titles we can batch-get short desc for

        # Setup Progress Dialog
        progress = QProgressDialog("Adding Wikipedia Pageviews...", "Stop", 0, len(self.nids)*2-len(self.nids)//-MAX_TITLES, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumSize(300,30)

        # Display tooltip message
        tooltip_msg = ""
        if fields_reused:
            tooltip_msg += "Re-using " + fields_listing(fields_reused) + ". "
        if fields_added:
            tooltip_msg += "Added new " + fields_listing(fields_added) + "."
        else:
            tooltip_msg += "No new fields added."
        tooltip(tooltip_msg, parent=self.parentWidget(), period=5000)

        # Popoulating the search phrases queue in prep for loop
        sps: queue.Queue[wiki.Wikifame] = queue.Queue()
        merge_string = self.wfd_ui_dict["merge_string_editor"].toPlainText()
        for nid in self.nids:
            search_phrase = self._merge_field_into_tag(merge_string,self.bmw.col.get_note(nid))
            wf = wiki.Wikifame(self.bmw,nid,search_phrase=search_phrase)
            wf.field_names["pageviews"] = field_names_new["pageviews"]
            wf.field_names["article"] = field_names_new["article"]
            wf.field_names["desc"] = field_names_new["desc"]
            wf.project = "en.wikipedia.org"
            sps.put(wf)

        # A bunch of queues
        buf_for_pageviews: queue.Queue[wiki.Wikifame] = queue.Queue()
        q_for_desc: queue.Queue[wiki.Wikifame] = queue.Queue()
        q_for_article_postfix: queue.Queue[wiki.Wikifame] = queue.Queue()
        
        prog: int = 0                   # Progress for the progress bar
        populated: int = 0              # The number of cards succesfully populated wih PVs
        http_errs: int = 0              # The number of http errors during the process
        no_arti_found_errs: int = 0     # The number of search phrases which resulted in 0 hits
        future_requests: Dict = {}      # A dictionary mapping each future to a (executor, List[Wikifame]) tuple
        
        # Multi-threaded query loop initialisation
        exe_se = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)     # search
        exe_pv = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)     # pageview
        exe_desc = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)   # description

        # Tracks the last RATE times the Wikipedia query API has been used
        req_times: Dict[concurrent.futures.ThreadPoolExecutor, List[float]] = {
            exe_se: [-2*PER] * RATE, exe_pv: [-2*PER] * RATE, exe_desc: [-2*PER] * RATE}

        # Tracks the total number of queries made of each type
        query_no: Dict[concurrent.futures.ThreadPoolExecutor, int] = {
            exe_se: 0, exe_pv: 0, exe_desc: 0}
            
        # Tracking the number of busy workers
        busy_exe: Dict[concurrent.futures.ThreadPoolExecutor,int] = {
            exe_se: 0, exe_pv: 0, exe_desc: 0}    

        # Multi-threaded query loop
        #   Search phrases -> Article URLs
        #   Article URLs -> Pageviews
        #   Article URLs -> Article Short Descriptions
        while future_requests or not sps.empty() or not buf_for_pageviews.empty() or not q_for_desc.empty():
            if progress.wasCanceled():
                break

            # IF (a) there are still search_phrases and (b) the search RATE searches ago was sent more than PER seconds ago and
            # (c) there is a thread ready to receive work: THEN give that thread work.
            while not sps.empty() and time.time() > req_times[exe_se][query_no[exe_se] % RATE] + PER * 1.01 and busy_exe[exe_se] < CONNECTIONS:
                req_times[exe_se][query_no[exe_se] % RATE] = time.time()
                query_no[exe_se] += 1
                busy_exe[exe_se] += 1
                sp = sps.get()
                future_requests[exe_se.submit(wiki.Wikifame.search_up_article, sp, timeout=TIMEOUT)] = (exe_se, [sp])

            done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

            # For each done future, get the result
            for future in done:
                er: bool = False
                try:
                    res: Optional[Union[wiki.Wikifame, List[str], Exception]] = future.result()
                except requests.HTTPError and wiki.Wikifame.NoArticlesFound as err:
                    if isinstance(err,requests.HTTPError):
                        http_errs += 1
                    if isinstance(err,wiki.Wikifame.NoArticlesFound):
                        no_arti_found_errs += 1
                    prog += 1
                    progress.setValue(prog)
                    er = True
                exe_list_wfs: Tuple[concurrent.futures.ThreadPoolExecutor,List[wiki.Wikifame]] = future_requests[future]
                (exe, list_wfs) = exe_list_wfs
                busy_exe[exe] -= 1

                if not er:
                    if exe == exe_se:
                        buf_for_pageviews.put(res)
                        q_for_desc.put(res)
                        q_for_article_postfix.put(res)
                    elif exe == exe_pv:
                        populated += 1
                    elif exe == exe_desc:
                        for j in range(len(list_wfs)):
                            list_wfs[j].set("desc",res[j])
                prog += 1
                progress.setValue(prog)
                del future_requests[future]
                
            # Same as top paragraph of loop for actual pageviews
            while not buf_for_pageviews.empty() and time.time() > req_times[exe_pv][query_no[exe_pv] % RATE] + PER * 1.01 and busy_exe[exe_pv] < CONNECTIONS:
                req_times[exe_pv][query_no[exe_pv] % RATE] = time.time()
                query_no[exe_pv] += 1
                busy_exe[exe_pv] += 1
                wf = buf_for_pageviews.get()
                future_requests[exe_pv.submit(wiki.Wikifame.fill_pageviews,wf,timeout=TIMEOUT)] = (exe_pv, [wf])

            # Same as top paragraph of loop for actual pageviews, but only activates when there are
            # more than 50 articles ready to do in a batch, or when there are less but this is the 
            # only thing left to do
            def b1() -> bool: return MAX_TITLES < q_for_desc.qsize()
            def b2() -> bool: return not future_requests and sps.empty() and buf_for_pageviews.empty()
            while (b1() or b2()) and time.time() > req_times[exe_desc][query_no[exe_desc] % RATE] + PER * 1.01 and busy_exe[exe_desc] < CONNECTIONS:
                req_times[exe_desc][query_no[exe_desc] % RATE] = time.time()
                query_no[exe_desc] += 1
                busy_exe[exe_desc] += 1
                l = min(MAX_TITLES, q_for_desc.qsize())
                list_for_desc: List[wiki.Wikifame] = []
                desc_strs: List[str] = []
                for j in range(l):
                    wff = q_for_desc.get()
                    arti = wff.fields["article"]
                    if arti is not None:
                        list_for_desc.append(wff)
                        desc_strs.append(arti)
                future_requests[exe_desc.submit(wiki.get_desc,desc_strs,timeout=TIMEOUT)] = (exe_desc, list_for_desc)

        # Multi-threaded query loop clean-up
        exe_se.shutdown(wait = False, cancel_futures = True)
        exe_pv.shutdown(wait = False, cancel_futures = True)
        exe_desc.shutdown(wait = False, cancel_futures = True)
        
        # This may be needed when many articles cannot be found (so the total number of batch
        # desc queries reduces dramatically)
        progress.setValue(progress.maximum())

        msg = "Added Pageview data for {} out of {} selected notes. {} search phrases not found.  {} errors".format(
            populated,len(self.nids),no_arti_found_errs,http_errs)
        showInfo(msg, textFormat="rich", parent=self)

        # Adding a pipe to each article, in prep for manual fixing phase
        while not q_for_article_postfix.empty():
            wf = q_for_article_postfix.get()
            wf.set("article",wf.note[wf.field_names["article"]]+" | ")

        self.close()

    def _setup_ui(self) -> None:
        """
        Sets up the UI for the Add Fame dialog.
        """

        def _insert_merge_tag() -> None:
            """
            Inserts the selected field wrapped in "{{ }}" to act as a merge tag.
            """

            if self.wfd_ui_dict["merge_tag_selector"].currentIndex() != 0:
                self.wfd_ui_dict["merge_string_editor"].insertPlainText("{{"+self.wfd_ui_dict["merge_tag_selector"].currentText()+"}}")
                self.wfd_ui_dict["merge_tag_selector"].setCurrentIndex(0)
            self.wfd_ui_dict["merge_string_editor"].setFocus()

        def _update_merged_string_example() -> None:
            """
            Generate and update the "Example" string under the textbox by merging with merge tags.
            """

            merge_string = self.wfd_ui_dict["merge_string_editor"].toPlainText()
            note = mw.col.get_note(self.nid)
            msg = "<b>Example:</b> " + self._merge_field_into_tag(merge_string, note)
            self.wfd_ui_dict["merged_string_example"].setTextFormat(Qt.RichText)
            self.wfd_ui_dict["merged_string_example"].setText(msg)
        
        main_vbox = QVBoxLayout()
        if True:
            ivbox = QVBoxLayout()
            desc_msg = "Add fields containing the number of Wikipedia pageviews "
            desc_msg+= "for an article (the first that Wikipedia search returns)."
            desc = QLabel(desc_msg)
            desc.setWordWrap(True)
            ivbox.addWidget(desc)
            selno = QLabel("<b>Notes selected:</b> " + str(len(self.nids)))
            ivbox.addWidget(selno)

            self.wfd_ui_dict = {}
            self.wfd_ui_dict["gb_name"] = "Get Wikipedia pageviews"
            self.wfd_ui_dict["new_field_placeholder"] = "Wiki Pageviews"

            ui = self.wfd_ui_dict
            ui["vbox"] = QVBoxLayout()
            if True:
                ui["merge_tag_selector_text"] = QFormLayout()
                if True:
                    ui["merge_tag_selector"] = QComboBox()
                    ui["merge_tag_selector"].addItems(["SELECT FIELD"] + self.fields)
                    ui["merge_tag_selector"].currentIndexChanged.connect(_insert_merge_tag)
                ui["merge_tag_selector_text"].addRow(QLabel("Insert field:"), ui["merge_tag_selector"])
                ui["merge_string_editor"] = QPlainTextEdit()

                ui["merged_string_example"] = QLabel("<b>Example:</b> ")
                ui["merged_string_example"].setWordWrap(True)
                ui["new_field_name_form"] = QFormLayout()
                if True:
                    ui["new_field_name_editor"] = QLineEdit()
                    ui["new_field_name_editor"].setText(ui["new_field_placeholder"])
                ui["new_field_name_form"].addRow(QLabel("Add Fame into Field:"), ui["new_field_name_editor"])
            ui["vbox"].addLayout(ui["merge_tag_selector_text"])
            ui["vbox"].addWidget(ui["merge_string_editor"])
            ui["vbox"].addWidget(ui["merged_string_example"])
            ui["vbox"].addLayout(ui["new_field_name_form"])
            ui["merge_string_editor"].textChanged.connect(_update_merged_string_example)

            button_box = QDialogButtonBox(Qt.Horizontal, self)
            done_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
            cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
            help_button = button_box.addButton(QDialogButtonBox.StandardButton.Help)
            done_button.setToolTip("Begin adding fame...")
            done_button.clicked.connect(lambda _: self.accept())
            cancel_button.clicked.connect(self.reject)

        main_vbox.addLayout(ivbox)
        main_vbox.addLayout(self.wfd_ui_dict["vbox"])
        main_vbox.addWidget(button_box)

        self.setLayout(main_vbox)
        self.wfd_ui_dict["merge_string_editor"].setFocus()
        self.setMinimumWidth(540)
        self.setMinimumHeight(230)
        self.resize(540,100)
        self.setWindowTitle("Add Fame...")


def add_fame(browser) -> None:
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    dialog = AddFameDialog(browser, nids)
    dialog.exec_()

def order_notes(browser) -> None:
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    tooltip("Selected! (To be developed)")
    # dialog = AddFameDialog(browser, nids)
    # dialog.exec_()

def setup_menu(browser : QMainWindow) -> None:
    menu = browser.form.menu_Notes
    menu.addSeparator()

    # Setup a new menu item, "Add Fame..."
    add_fameAction = QAction("Add Fame...", mw)
    menu.addAction(add_fameAction)
    qconnect(add_fameAction.triggered, lambda: add_fame(browser))

    # Setup a new menu item, "Order Notes..."
    add_fameAction = QAction("Order Notes by...", mw)
    menu.addAction(add_fameAction)
    qconnect(add_fameAction.triggered, lambda: order_notes(browser))

gui_hooks.browser_menus_did_init.append(setup_menu)

