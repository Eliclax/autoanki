from math import ceil
from aqt import mw, gui_hooks, AnkiQt
from aqt.utils import qconnect, tooltip, showWarning, showInfo
from aqt.qt import *
from anki.notes import NoteId, Note
from anki.models import NotetypeDict, NotetypeId, ModelManager
from aqt.fields import *

from time import sleep
import re
from typing import Sequence, Optional, Union, List

from . import wiki
from urllib import error
import concurrent.futures
import queue
import time
import requests

TESTING = False

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
            msg = "<b>Adding Wikipedia fame to a single note</b><br><br>You have selected a single note.  Due to a weird bug I can't figure out, adding "
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
                # tooltip("New field \"" + self.fDict[0]["useFieldName"].text() + "\" added.", parent=self.parentWidget())
                QDialog.accept(self)

            update_notetype_legacy(parent=self.bmw, notetype=self.model).success(on_done).run_in_background()
            sleep(0.2) # The previous command requires time to propagate its changes

        # Add wikipedia fame?
        if self.fDict[0]["gb"].isChecked():
            # Check if we have a connection to Wikipedia.
            try:
                wiki.search_article_url("Noodles")
            except error.URLError as err:
                self._handle_network_error(err)
                return

            CONNECTIONS = 100
            RATE = 100
            PER = 1
            TIMEOUT = 5
            MAX_TITLES = 50

            # Setup Progress Dialog
            progress = QProgressDialog("Adding Wikipedia Pageviews...", "Stop", 0, len(self.nids)*2-len(self.nids)//-MAX_TITLES, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setMinimumSize(300,30)

            # Add necessary fields
            field_name = self.fDict[0]["useFieldName"].text()
            _add_field(field_name)
            _add_field(field_name + " (URL)")
            _add_field(field_name + " (Description)")
            _add_field(field_name + " (URL fixed)")
            tooltip("New fields based on \"" + self.fDict[0]["useFieldName"].text() + "\" added.", parent=self.parentWidget())

            search_times = [-2*PER] * RATE
            pv_times = [-2*PER] * RATE
            desc_times = [-2*PER] * RATE
            search_no = 0
            pv_no = 0
            desc_no = 0

            sps: queue.Queue[wiki.Wikifame] = queue.Queue()
            merge_string = self.fDict[0]["edit"].toPlainText()
            for nid in self.nids:
                search_phrase = self._merge_field_into_tag(merge_string,self.bmw.col.get_note(nid))
                wf = wiki.Wikifame(self.bmw,nid,search_phrase=search_phrase)
                wf.field_names["pageviews"] = self.fDict[0]["useFieldName"].text()
                wf.field_names["article"] = self.fDict[0]["useFieldName"].text() + " (URL)"
                wf.field_names["article_fixed"] = self.fDict[0]["useFieldName"].text() + " (URL fixed)"
                wf.field_names["desc"] = self.fDict[0]["useFieldName"].text() + " (Description)"
                wf.project = "en.wikipedia.org"
                sps.put(wf)

            buf_for_pageviews: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_desc: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_PV_ints: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_article_strs: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_desc_strs: queue.Queue[wiki.Wikifame] = queue.Queue()
            #list_for_desc: List[wiki.Wikifame] = []
            
            prog: int = 0                   # Progress for the progress bar
            populated: int = 0              # The number of cards succesfully populated wih PVs
            http_errs: int = 0              # The number of http errors during the process
            no_arti_found_errs: int = 0     # The number of search phrases which resulted in 0 hits
            future_requests: Dict = {}      # A dictionary mapping each future to a (executor, List[Wikifame]) tuple
            
            # Multi-threaded query loop initialisation
            executor_search = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            executor_pv = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            executor_desc = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            busy_search: int = 0
            busy_pv: int = 0
            busy_desc: int = 0

            # Multi-threaded query loop
            while future_requests or not sps.empty() or not buf_for_pageviews.empty() or not q_for_desc.empty():
                if progress.wasCanceled():
                    break

                # IF (a) there are still searchPhrases and (b) it has been PER seconds since RATE searches ago and
                # (c) there is a thread ready to receive work: THEN give that thread work.
                while not sps.empty() and time.time() > search_times[search_no % RATE] + PER * 1.01 and busy_search < CONNECTIONS:
                    search_times[search_no % RATE] = time.time()
                    search_no += 1
                    busy_search += 1
                    sp = sps.get()
                    future_requests[executor_search.submit(wiki.Wikifame.search_up_article,sp,timeout=TIMEOUT)] = (executor_search, [sp])

                
                done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

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
                    exe, listWfs = future_requests[future]
                    if exe == executor_search:
                        busy_search -= 1
                        if not er:
                            buf_for_pageviews.put(res)
                            q_for_desc.put(res)
                            q_for_article_strs.put(res)
                            #list_for_desc.append(res)
                    elif exe == executor_pv:
                        busy_pv -= 1
                        if not er:
                            populated += 1
                            q_for_PV_ints.put(res)
                    elif exe == executor_desc:
                        busy_desc -= 1
                        if not er:
                            for j in range(len(listWfs)):
                                listWfs[j].set("desc",res[j])
                    prog += 1
                    progress.setValue(prog)
                    del future_requests[future]
                    
                # Same as top paragraph of loop for actual pageviews
                while not buf_for_pageviews.empty() and time.time() > pv_times[pv_no % RATE] + PER * 1.01 and busy_pv < CONNECTIONS:
                    pv_times[pv_no % RATE] = time.time()
                    pv_no += 1
                    busy_pv += 1
                    wf = buf_for_pageviews.get()
                    future_requests[executor_pv.submit(wiki.Wikifame.fill_pageviews,wf,timeout=TIMEOUT)] = (executor_pv, [wf])

                # Same as top paragraph of loop for actual pageviews
                # while not q_for_desc.empty() and time.time() > desc_times[desc_no % RATE] + PER * 1.01 and busy_desc < CONNECTIONS:
                #     desc_times[desc_no % RATE] = time.time()
                #     desc_no += 1
                #     busy_desc += 1
                #     wf = q_for_desc.get()
                #     future_requests[executor_desc.submit(wiki.Wikifame.fill_description,wf,timeout=TIMEOUT)] = (executor_desc, [wf])

                def b1() -> bool: return MAX_TITLES < q_for_desc.qsize()
                def b2() -> bool: return not future_requests and sps.empty() and buf_for_pageviews.empty()
                while (b1() or b2()) and time.time() > desc_times[desc_no % RATE] + PER * 1.01 and busy_desc < CONNECTIONS:
                    desc_times[desc_no % RATE] = time.time()
                    desc_no += 1
                    busy_desc += 1
                    l = min(MAX_TITLES, q_for_desc.qsize())
                    list_for_desc: List[wiki.Wikifame] = []
                    desc_strs: List[str] = []
                    for j in range(l):
                        wff = q_for_desc.get()
                        arti = wff.fields["article"]
                        if arti is not None:
                            list_for_desc.append(wff)
                            desc_strs.append(arti)
                    future_requests[executor_desc.submit(wiki.get_desc,desc_strs,timeout=TIMEOUT)] = (executor_desc, list_for_desc)

            #sleep(1)

            # Multi-threaded query loop clean-up
            executor_search.shutdown(wait = False, cancel_futures = True)
            executor_pv.shutdown(wait = False, cancel_futures = True)
            executor_desc.shutdown(wait = False, cancel_futures = True)

            # print(cleanedWfs)
            # print(cleanedStrs)

            # i = 0
            # while i < len(list_for_desc) or future_requests:
            #     while i < len(list_for_desc) and time.time() > desc_times[desc_no % RATE] + PER * 1.01 and busy_desc < CONNECTIONS:
            #         print("Entering Loop A")
            #         desc_times[desc_no % RATE] = time.time()
            #         desc_no += 1
            #         busy_desc += 1
            #         l = min(MAX_TITLES, len(list_for_desc)-i)
            #         future_requests[executor_desc.submit(wiki.get_desc,cleanedStrs[i:i+l],timeout=TIMEOUT)] = cleanedWfs[i:i+l]
            #         i += MAX_TITLES

            #     done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

            #     for future in done:
            #         print("Entering B")
            #         busy_desc -= 1
            #         res: Optional[List[str]] = future.result()
            #         wfs: List[wiki.Wikifame] = future_requests[future]
            #         if res is not None:
            #             if len(res) == 1:
            #                 res *= 2
            #                 wfs *= 2
            #             print(res)
            #             for j in range(len(res)):
            #                 wfs[j].set("desc",res[j])
            #                 note = wfs[j].note
            #                 self.bmw.col.update_note(note)
            #                 print(wfs[j].field_names["desc"])
            #                 print("2: "  +self.bmw.col.get_note(wfs[j].nid)[wfs[j].field_names["desc"]])
            #                 print("2.1: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])
            #             prog += 1

            #             progress.setValue(prog)
            #         else:
            #             note = wfs[j].note
            #             self.bmw.col.update_note(note)

            #         del future_requests[future]

            # print("2.3: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])
            # self.bmw.col.update_note(self.bmw.col.get_note(self.nids[0]))
            # #executor_desc.shutdown(wait = False)
            # print("2.4: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

            progress.setValue(progress.maximum())

            msg = "Added Pageview data for {} out of {} selected notes. {} search phrases not found.  {} errors".format(
                populated,len(self.nids),no_arti_found_errs,http_errs)
            # print("2.5: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
            # print("2.5: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])
            showInfo(msg, textFormat="rich", parent=self)
            # print("2.6: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
            # print("2.6: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

            for nid in self.nids:
                search_phrase = self._merge_field_into_tag(merge_string,self.bmw.col.get_note(nid))
                wf = wiki.Wikifame(self.bmw,nid,search_phrase=search_phrase)
                wf.field_names["pageviews"] = self.fDict[0]["useFieldName"].text()
                wf.field_names["article"] = self.fDict[0]["useFieldName"].text() + " (URL)"
                wf.field_names["article_fixed"] = self.fDict[0]["useFieldName"].text() + " (URL fixed)"
                wf.field_names["desc"] = self.fDict[0]["useFieldName"].text() + " (Description)"
                wf.project = "en.wikipedia.org"
                sps.put(wf)

            wf = sps.get()

        # while not q_for_article_strs.empty():
        #     wf = q_for_article_strs.get()
        #     wf.note[wf.field_names["article"]] = str(wf.fields["article"])
        #     wf.mw.col.update_note(wf.note)

        # while not q_for_PV_ints.empty():
        #     wf = q_for_PV_ints.get()
        #     wf.note[wf.field_names["pageviews"]] = str(wf.fields["pageviews"])
        #     wf.mw.col.update_note(wf.note)

        while not q_for_desc_strs.empty():
            wf = q_for_desc_strs.get()
            wf.note[wf.field_names["desc"]] = str(wf.fields["desc"])
            wf.mw.col.update_note(wf.note)

        self.close()

        # print("2.7: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
        # print("2.7: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

        self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"] = "HI!!"
        self.bmw.col.update_note(self.bmw.col.get_note(self.nids[0]))
        # print("2.8: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
        # print("2.8: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

    def _setup_ui(self) -> None:
        """
        Sets up the UI for the Add Fame dialog.
        """

        def _insert_field(i: int) -> None:
            """
            Inserts the selected field wrapped in "{{ }}" to act as a merge tag.

            :param i: An int, the index of the field selected.
            """

            if self.fDict[i]["insertSelect"].currentIndex() != 0:
                self.fDict[i]["edit"].insertPlainText("{{"+self.fDict[i]["insertSelect"].currentText()+"}}")
                self.fDict[i]["insertSelect"].setCurrentIndex(0)
            self.fDict[i]["edit"].setFocus()

        def _update_example(i: int) -> None:
            """
            Generate and update the "Example" string under the textbox by merging with merge tags.

            :param i: 0 = Wiki, 1 = Google
            """

            merge_string = self.fDict[i]["edit"].toPlainText()
            note = mw.col.get_note(self.nid)
            msg = "<b>Example:</b> " + self._merge_field_into_tag(merge_string, note)
            self.fDict[i]["example"].setTextFormat(Qt.RichText)
            self.fDict[i]["example"].setText(msg)
        
        main_vbox = QVBoxLayout()
        if True:
            ivbox = QVBoxLayout()
            desc_msg = "Add fields containing the number of Wikipedia pageviews "
            desc_msg+= "for an article (the first that Wikipedia search returns) and/or "
            desc_msg+= "the number of Google hits for a search term.  Note: ensure no field begins with '{'."
            desc_msg+= "Note: A super weird bug prevents proper function when only 1 card is selected."
            desc = QLabel(desc_msg)
            desc.setWordWrap(True)
            ivbox.addWidget(desc)
            selno = QLabel("<b>Notes selected:</b> " + str(len(self.nids)))
            ivbox.addWidget(selno)
            #ivbox.insertStretch(1, stretch=1)

            fDictNo = 2
            self.fDict = [{} for a in range(fDictNo)]
            self.fDict[0]["gbName"] = "Get Wikipedia pageviews"
            self.fDict[1]["gbName"] = "Get Google hits (in development!)"
            self.fDict[0]["newFieldPlaceholder"] = "Wiki Pageviews"
            self.fDict[1]["newFieldPlaceholder"] = "Google Hits"

            for i in range(2):
                fd = self.fDict[i]
                fd["gb"] = QGroupBox(fd["gbName"])
                fd["gb"].setCheckable(True)
                if TESTING and i == 1:
                    fd["gb"].setChecked(False)
                if True:
                    fd["vbox"] = QVBoxLayout()
                    if True:
                        fd["insertField"] = QFormLayout()
                        if True:
                            fd["insertSelect"] = QComboBox()
                            fd["insertSelect"].addItems(["SELECT FIELD"] + self.fields)
                            fd["insertSelect"].currentIndexChanged.connect(lambda _, x = i: _insert_field(x))
                        fd["insertField"].addRow(QLabel("Insert field:"), fd["insertSelect"])
                        fd["edit"] = QPlainTextEdit()
                        if TESTING and i == 0:
                            fd["edit"].insertPlainText("{{Name}}")

                        fd["example"] = QLabel("<b>Example:</b> ")
                        fd["example"].setWordWrap(True)
                        fd["useField"] = QFormLayout()
                        if True:
                            fd["useFieldName"] = QLineEdit()
                            fd["useFieldName"].setText(fd["newFieldPlaceholder"])
                            #fd["useFieldName"].currentIndexChanged.connect(lambda _, x = i: _insert_field(x))
                        fd["useField"].addRow(QLabel("Add Fame into Field:"), fd["useFieldName"])
                    fd["vbox"].addLayout(fd["insertField"])
                    fd["vbox"].addWidget(fd["edit"])
                    fd["vbox"].addWidget(fd["example"])
                    fd["vbox"].addLayout(fd["useField"])
                fd["gb"].setLayout(fd["vbox"])
                fd["edit"].textChanged.connect(lambda x = i: _update_example(x))

            button_box = QDialogButtonBox(Qt.Horizontal, self)
            done_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
            cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
            help_button = button_box.addButton(QDialogButtonBox.StandardButton.Help)
            done_button.setToolTip("Begin adding fame...")
            done_button.clicked.connect(lambda _: self.accept())
            cancel_button.clicked.connect(self.reject)

        main_vbox.addLayout(ivbox)
        main_vbox.addWidget(self.fDict[0]["gb"])
        #main_vbox.addWidget(self.fDict[1]["gb"])
        main_vbox.addWidget(button_box)

        self.setLayout(main_vbox)
        self.fDict[0]["edit"].setFocus()
        self.setMinimumWidth(540)
        self.setMinimumHeight(550)
        self.resize(540,330)
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

