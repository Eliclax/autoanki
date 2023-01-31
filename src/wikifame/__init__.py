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
                # tooltip("New field \"" + self.ui_new_field_name_editor"].text() + "\" added.", parent=self.parentWidget())
                QDialog.accept(self)

            update_notetype_legacy(parent=self.bmw, notetype=self.model).success(on_done).run_in_background()
            sleep(0.2) # The previous command requires time to propagate its changes

        # Check if we have a connection to Wikipedia.
        try:
            wiki.search_article_url("Noodles")
        except error.URLError as err:
            self._handle_network_error(err)
            return

        # Check if the lang_code is valid
        try:
            requests.get(f"https://{self.ui_lang_code_QLineEdit.text()}.wikipedia.org")
        except requests.HTTPError as err:
            self._handle_network_error(err)
            return



        # Proper English phrasing for fields
        def fields_listing(fields: List[str]) -> str:
            if len(fields) == 0: return ""
            if len(fields) == 1: return f"field \"{fields[0]}\""
            if len(fields) == 2: return f"fields \"{fields[0]}\" and \"{fields[1]}\""
            if len(fields) >= 3: return "fields \"" + "\", \"".join(fields[0:-1]) + f"\", and \"{fields[-1]}\""

        # Add necessary fields
        fn = self.ui_new_field_name_QLineEdit.text()
        field_names_new: Dict[str, str] = {
            "pageviews": fn, "article": fn+" (URL)", "desc": fn + " (Description)", "num_of_langs": fn + " (Languages)"}
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

        CONNECTIONS = 100               # Number of workers to use for the threads
        RATE = 100                      # Ratelimit of RATE per PER seconds
        PER = 1                         # Ratelimit of RATE per PER seconds
        TIMEOUT = 5                     # Amount of time to wait for an http request
        MAX_TITLES = 50                 # Maximum number of titles we can batch-get short desc for

        # Setup Progress Dialog
        progress = QProgressDialog("Adding Wikifame Data...", "Stop", 0, len(self.nids)*3, self)
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

        # A bunch of queues
        # Populating the search phrases queue in prep for loop
        q_wfs_with_sp: queue.Queue[wiki.Wikifame] = queue.Queue()           # Queue before step 1
        buf_with_pos_articles: queue.Queue[wiki.Wikifame] = queue.Queue() # Buffer between step 1 and 2
        buf_for_pageviews: queue.Queue[wiki.Wikifame] = queue.Queue()     # Buffer between step 2 and 3
        q_for_updating_notes: queue.Queue[wiki.Wikifame] = queue.Queue() # Queue after step 3, for adding a " | " to the URL after processing

        wfs: List[wiki.Wikifame] = []

        # Populating q_wfs_with_sp
        merge_string = self.ui_merge_string_QPlainTextEdit.toPlainText()
        for nid in self.nids:
            search_phrase = self._merge_field_into_tag(merge_string,self.bmw.col.get_note(nid))
            lang_code = self.ui_lang_code_QLineEdit.text()
            keywords = self.ui_keywords_QLineEdit.text().split(",")
            for i in range(len(keywords)):
                keywords[i].strip()
            wf = wiki.Wikifame(nid=nid,search_phrase=search_phrase,lang_code=lang_code,keywords=keywords)
            q_wfs_with_sp.put(wf)
            wfs.append(wf)

        prog: int = 0                   # Progress for the progress bar
        pageviews_gotten: int = 0              # The number of cards succesfully populated wih PVs
        http_errs: int = 0              # The number of http errors during the process
        no_arti_found_errs: int = 0     # The number of search phrases which resulted in 0 hits
        future_requests: Dict = {}      # A dictionary mapping each future to a (executor, List[Wikifame]) tuple
        
        class ThrottledThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
            def __init__(
                self,
                max_workers: int = CONNECTIONS,
                rate: int= RATE,
                per: float = PER,
                timeout: float = TIMEOUT,
                max_titles: Optional[int] = None,
                func = None,
                q: queue.Queue = None,
                )-> None:
                
                self.rate = rate
                self.per = per
                self.timeout = timeout
                self.max_titles = max_titles
                self.busy = 0
                self.query_no = 0
                self.search_times = [-2*PER]*RATE
                self.max_workers = max_workers
                self.func = func
                self.q = q
                super().__init__(max_workers=max_workers)

        # Multi-threaded query loop initialisation
        exe_mw = ThrottledThreadPoolExecutor(max_workers=CONNECTIONS, func=wiki.Wikifame.fill_possible_articles, q=q_wfs_with_sp)                 # mediawiki API
        exe_wd = ThrottledThreadPoolExecutor(max_workers=CONNECTIONS, func=wiki.Wikifame.wikidata_on_possible_articles, q=buf_with_pos_articles)  # wikidata API
        exe_wm = ThrottledThreadPoolExecutor(max_workers=CONNECTIONS, func=wiki.Wikifame.fill_pageviews, q=buf_for_pageviews)                     # wikimedia REST API
        exes: List[ThrottledThreadPoolExecutor] = [exe_mw, exe_wd, exe_wm]

        # Multi-threaded query loop
        #   Search phrase -> Possible Article URLs (MediaWiki API using fill_possible_articles)
        #   Possible Article URLs -> Short Descriptions -> Get "correct" URL and description (MediaWiki API using wikidata_on_possible_articles)
        #   Correct Article URL -> Pageview (REST API using fill_pageviews)
        while future_requests or not q_wfs_with_sp.empty() or not buf_with_pos_articles.empty() or not buf_for_pageviews.empty():
            if progress.wasCanceled():
                break

            done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

            # For each done future, get the result
            for future in done:
                er: bool = False
                try:
                    res: Optional[Union[wiki.Wikifame, List[str], Exception]] = future.result()
                except Exception as err:
                    if isinstance(err, requests.HTTPError):
                        http_errs += 1
                    elif isinstance(err, wiki.Wikifame.NoArticlesFound):
                        no_arti_found_errs += 1
                    elif err.args[0] == "ERROR: No Search Phrase":
                        pass
                    else:
                        raise err
                    if exe == exe_mw:
                        prog += 2
                    elif exe == exe_wd:
                        prog += 1
                    er = True
                exe_list_wfs: Tuple[ThrottledThreadPoolExecutor, List[wiki.Wikifame]] = future_requests[future]
                (exe, list_wfs) = exe_list_wfs
                exe.busy -= 1

                if not er:
                    if exe == exe_mw:
                        buf_with_pos_articles.put(res)
                    elif exe == exe_wd:
                        buf_for_pageviews.put(res)
                        q_for_updating_notes.put(res)
                        pageviews_gotten += 1
                    elif exe == exe_wm:
                        pass
                        # for j in range(len(list_wfs)):
                        #     list_wfs[j].set("desc",res[j])
                prog += 1
                progress.setValue(prog)
                del future_requests[future]

            for exe in exes:
                # IF (a) there are still search_phrases and (b) the search RATE searches ago was sent more than PER seconds ago and
                # (c) there is a thread ready to receive work: THEN give that thread work.
                while not exe.q.empty() and time.time() > exe.search_times[exe.query_no % exe.rate] + exe.per * 1.01 and exe.busy < exe.max_workers:
                    exe.search_times[exe.query_no % exe.rate] = time.time()
                    exe.query_no += 1
                    exe.busy += 1
                    wf = exe.q.get()
                    future_requests[exe.submit(exe.func, wf, timeout=exe.timeout)] = (exe, [wf])

            # # IF (a) there are still search_phrases and (b) the search RATE searches ago was sent more than PER seconds ago and
            # # (c) there is a thread ready to receive work: THEN give that thread work.
            # while not wfs_with_sp.empty() and time.time() > exe_mw.search_times[exe_mw.query_no % exe_mw.rate] + exe_mw.per * 1.01 and exe_mw.busy < exe_mw.max_workers:
            #     exe_mw.search_times[exe_mw.query_no % exe_mw.rate] = time.time()
            #     exe_mw.query_no += 1
            #     exe_mw.busy += 1
            #     wf_with_sp = wfs_with_sp.get()
            #     future_requests[exe_mw.submit(wiki.Wikifame.fill_possible_articles, wf_with_sp, timeout=exe_mw.timeout)] = (exe_mw, [wf_with_sp])
                
            # # Same as above paragraph for article resolution
            # while not buf_with_pos_articles.empty() and time.time() > exe_wd.search_times[exe_wd.query_no % exe_wd.rate] + exe_wd.per * 1.01 and exe_wd.busy < exe_wd.max_workers:
            #     exe_wd.search_times[exe_wd.query_no % exe_wd.rate] = time.time()
            #     exe_wd.query_no += 1
            #     exe_wd.busy += 1
            #     wf = buf_with_pos_articles.get()
            #     future_requests[exe_wd.submit(wiki.Wikifame.fill_pageviews,wf,timeout=exe_wd.timeout)] = (exe_wd, [wf])

            # # Same as top paragraph of loop for actual pageviews, but only activates when there are
            # # more than 50 articles ready to do in a batch, or when there are less but this is the 
            # # only thing left to do
            # def b1() -> bool: return MAX_TITLES < q_for_desc.qsize()
            # def b2() -> bool: return not future_requests and wfs_with_sp.empty() and buf_with_pos_articles.empty()
            # while (b1() or b2()) and time.time() > exe_wm.search_times[exe_wm.query_no % exe_wm.rate] + exe_wm.per * 1.01 and exe_wm.busy < exe_wm.max_workers:
            #     exe_wm.search_times[exe_wm.query_no % exe_wm.rate] = time.time()
            #     exe_wm.query_no += 1
            #     exe_wm.busy += 1
            #     l = min(MAX_TITLES, q_for_desc.qsize())
            #     list_for_desc: List[wiki.Wikifame] = []
            #     desc_strs: List[str] = []
            #     for j in range(l):
            #         wff = q_for_desc.get()
            #         arti = wff.fields["article"]
            #         if arti is not None:
            #             list_for_desc.append(wff)
            #             desc_strs.append(arti)
            #     future_requests[exe_wm.submit(wiki.get_desc,desc_strs,timeout=TIMEOUT)] = (exe_wm, list_for_desc)

        # Multi-threaded query loop clean-up
        for exe in exes:
            exe.shutdown(wait = False, cancel_futures = True)

        # exe_mw.shutdown(wait = False, cancel_futures = True)
        # exe_wd.shutdown(wait = False, cancel_futures = True)
        # exe_wm.shutdown(wait = False, cancel_futures = True)

        for field_added in fields_added:
            _add_field(field_added)
        
        # This may be needed when many articles cannot be found (so the total number of batch
        # desc queries reduces dramatically)
        progress.setValue(progress.maximum())

        msg = "Added Pageview data for {} out of {} selected notes.  {} search phrases not found.  {} errors. ".format(
            pageviews_gotten,len(self.nids),no_arti_found_errs,http_errs)
        msg += "\n\nAny notes without a pageview or number of languages count are tagged with \"Wiki_Warning\"."
        showInfo(msg, textFormat="rich", parent=self)

        # Adding a pipe to each article, in prep for manual fixing phase
        while not q_for_updating_notes.empty():
            wf = q_for_updating_notes.get()
            print(f"Doing {wf.article}")
            note = self.bmw.col.get_note(wf.nid)
            note[field_names_new["pageviews"]] = str(wf.pageviews)
            note[field_names_new["article"]] = wf.article+" | "
            note[field_names_new["desc"]] = wf.desc
            note[field_names_new["num_of_langs"]] = str(wf.num_of_langs)
            print(wf.nid)
            self.bmw.col.update_note(note)

        for wf in wfs:
            print(f"Checking {self.nid} for warnings...")
            if wf.warning:
                print("WARNING: Wiki Warning")
                note = self.bmw.col.get_note(wf.nid)
                note.add_tag("Wiki_Warning")
                self.bmw.col.update_note(note)

        print("DONE")

        #     note.flush()
        #     qq.append(note)

        # self.bmw.col.update_notes(qq)

        self.close()

    def _setup_ui(self) -> None:
        """
        Sets up the UI for the Add Fame dialog.
        """

        def _insert_merge_tag() -> None:
            """
            Inserts the selected field wrapped in "{{ }}" to act as a merge tag.
            """

            if ui_merge_tag_selector.currentIndex() != 0:
                self.ui_merge_string_QPlainTextEdit.insertPlainText("{{"+ui_merge_tag_selector.currentText()+"}}")
                ui_merge_tag_selector.setCurrentIndex(0)
            self.ui_merge_string_QPlainTextEdit.setFocus()

        def _update_merged_string_example() -> None:
            """
            Generate and update the "Example" string under the textbox by merging with merge tags.
            """

            merge_string = self.ui_merge_string_QPlainTextEdit.toPlainText()
            note = mw.col.get_note(self.nid)
            msg = "<b>Example:</b> " + self._merge_field_into_tag(merge_string, note)
            ui_merge_string_example.setTextFormat(Qt.RichText)
            ui_merge_string_example.setText(msg)
        
        ui_main_vbox = QVBoxLayout()
        if True:
            if True:
                ui_desc_msg = "Add fields containing the number of Wikipedia pageviews "
                ui_desc_msg+= "for an article (the first that Wikipedia search returns)."
            ui_desc = QLabel(ui_desc_msg)
            ui_desc.setWordWrap(True)

            ui_selno = QLabel("<b>Notes selected:</b> " + str(len(self.nids)))
            
            ui_gbox = QGroupBox("Merge String")
            ui_gbox.setCheckable(True)
            if True:
                ui_gbvbox = QVBoxLayout()
                if True:
                    ui_merge_tag_selector_form = QFormLayout()
                    if True:
                        ui_merge_tag_selector = QComboBox()
                        ui_merge_tag_selector.addItems(["SELECT FIELD"] + self.fields)
                        ui_merge_tag_selector.currentIndexChanged.connect(_insert_merge_tag)
                    ui_merge_tag_selector_form.addRow(QLabel("Insert field:"), ui_merge_tag_selector)
                    self.ui_merge_string_QPlainTextEdit = QPlainTextEdit()
                    self.ui_merge_string_QPlainTextEdit.textChanged.connect(_update_merged_string_example)
                    ui_merge_string_example = QLabel("<b>Example:</b> ")
                    ui_merge_string_example.setWordWrap(True)
                ui_gbvbox.addLayout(ui_merge_tag_selector_form)
                ui_gbvbox.addWidget(self.ui_merge_string_QPlainTextEdit)
                ui_gbvbox.addWidget(ui_merge_string_example)
            ui_gbox.setLayout(ui_gbvbox)

            ui_misc_form = QFormLayout()
            if True:
                self.ui_lang_code_QLineEdit = QLineEdit()
                self.ui_lang_code_QLineEdit.setText("en")
                self.ui_keywords_QLineEdit = QLineEdit()
                self.ui_new_field_name_QLineEdit = QLineEdit()
                self.ui_new_field_name_QLineEdit.setText("Wiki Pageviews")
            ui_misc_form.addRow(QLabel("Keywords (comma separated):"), self.ui_keywords_QLineEdit)
            ui_misc_form.addRow(QLabel("Language Code:"), self.ui_lang_code_QLineEdit)
            ui_misc_form.addRow(QLabel("Add Fame into Field:"), self.ui_new_field_name_QLineEdit)

            ui_button_box = QDialogButtonBox(Qt.Horizontal, self)
            if True:
                ui_done_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Ok)
                ui_cancel_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
                ui_help_button = ui_button_box.addButton(QDialogButtonBox.StandardButton.Help)
                ui_done_button.setToolTip("Begin adding fame...")
                ui_done_button.clicked.connect(self.accept)
                ui_cancel_button.clicked.connect(self.reject)

        ui_main_vbox.addWidget(ui_desc)
        ui_main_vbox.addWidget(ui_selno)
        ui_main_vbox.addWidget(ui_gbox)
        ui_main_vbox.addLayout(ui_misc_form)
        ui_main_vbox.addWidget(ui_button_box)

        self.setLayout(ui_main_vbox)
        self.ui_merge_string_QPlainTextEdit.setFocus()
        self.setMinimumWidth(540)
        self.setMinimumHeight(330)
        self.resize(540,300)
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

