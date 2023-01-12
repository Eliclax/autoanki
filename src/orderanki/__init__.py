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
        note: Note = self.bmw.col.getNote(self.nid)
        self.model: Optional[Union[NotetypeDict, NotetypeId]] = note.model()
        self.fields = self.bmw.col.models.fieldNames(self.model)
        self._setupUi()
        self.currentIdx: Optional[int] = None

    def _handleNetworkError(self, err: Exception, msg: str = "") -> None:
        if isinstance(err, requests.HTTPError):
            txt = str(err.code) + " HTTP ERROR"
        else:
            txt = tr.addons_please_check_your_internet_connection() + "\n\nError: " + str(err.reason)
        showWarning(msg + "\n\n" + txt, textFormat="rich", parent=self)

    def _mergeFieldIntoTag(self, mergeString: str, note: Note) -> str:
        """
        Merge the tags from a given Note into a merge String.

        :param mergeString:  The string containing merge tags
        :param note:  The note
        """

        mergeResult = ""
        mergeRe = r"\{\{[^\{].*?\}\}"
        se = re.search(mergeRe, mergeString)
        while se is not None:
            fieldName = se.group()[2:-2]
            # note = mw.col.get_note(self.nid)
            noteValues = [item for item in note.items() if item[0] == fieldName]
            if len(noteValues) >= 1:
                mergeResult += mergeString[0:se.span()[0]] + str(noteValues[0][1])
            else:
                mergeResult += mergeString[0:se.span()[1]]
            mergeString = mergeString[se.span()[1]:]
            se = re.search(mergeRe, mergeString)
        mergeResult += mergeString
        return mergeResult

    def _getFields(self) -> List[str]:
        """
        Returns a list of field names for the model that the notes are based on.

        :return: A list of field names for the notes' model
        """

        return self.bmw.col.models.fieldNames(self.model)

    # See https://github.com/ankitects/anki/blob/d110c4916cf1d83fbeae48ae891515c79a412018/qt/aqt/fields.py#L142
    def _uniqueName(self, txt: str, ignoreOrd: Optional[int] = None) -> Optional[str]:
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
        def _addField(fieldName: str) -> None:
            """
            Add a field to the model called fieldName.

            :param fieldName: The name of the field to add.
            """

            self.mm = ModelManager(self.bmw.col)
            self.change_tracker = ChangeTracker(self.bmw)
            self.currentIdx = len(self.model["flds"])
            # fieldName = [self.fDict[0]["useFieldName"].text(), self.fDict[1]["useFieldName"].text()]
            if self.fDict[0]["gb"].isChecked():        
                fieldName = self._uniqueName(fieldName)
                if not fieldName:
                    return
                if not self.change_tracker.mark_schema():
                    return
                f = self.mm.new_field(fieldName)
                self.mm.add_field(self.model, f)

            def on_done(changes: OpChanges) -> None:
                tooltip("New field \"" + self.fDict[0]["useFieldName"].text() + "\" added.", parent=self.parentWidget())
                QDialog.accept(self)

            update_notetype_legacy(parent=self.bmw, notetype=self.model).success(on_done).run_in_background()
            sleep(0.1) # The previous command requires time to propagate its changes

        # Check if we have a connection to Wikipedia.
        try:
            wiki.searchArticleUrl("Noodles")
        except error.URLError as err:
            self._handleNetworkError(err)
            return

        _addField(self.fDict[0]["useFieldName"].text())

        # Add wikipedia fame?
        if self.fDict[0]["gb"].isChecked():
            # Setup Progress Dialog
            progress = QProgressDialog("Adding Wikipedia Pageviews...", "Stop", 0, len(self.nids)*2, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setMinimumSize(300,30)

            CONNECTIONS = 30
            TIMEOUT = 5
            RATE = 30
            PER = 1

            def _searchWiki(sp: str, ti: float = TIMEOUT) -> str:
                """
                Wrapper for wiki.searchArticleUrl()
                """
                try:
                    article = wiki.searchArticleUrl(sp,ti)
                except requests.HTTPError as err:
                    #self._handleNetworkError(err)
                    raise
                return article

            def _getPageviews(
                ar: Union[str, None], #article
                pr: str = "en.wikipedia.org", #project
                ac: str = "all-access", #access
                ag: str = "user", #agent
                gr: str = "monthly", #granulatiry
                st: str = "20150701", #start
                en: str = "20230101", #end
                ti: float = TIMEOUT #timeout
                ) -> int:
                """
                Wrapped for wiki.getPageviews()
                """

                try:
                    pv: int = wiki.getPageviews(ar,pr,ac,ag,gr,st,en,ti)
                except requests.HTTPError as err:
                    #self._handleNetworkError(err)
                    raise
                return pv

            searchTimes = [-PER] * RATE
            pVTimes = [-PER] * RATE
            searchNo = 0
            pVNo = 0

            sps: queue.Queue = queue.Queue()
            mergeString = self.fDict[0]["edit"].toPlainText()
            [sps.put((self._mergeFieldIntoTag(mergeString,self.bmw.col.getNote(nid)),nid)) for nid in self.nids]

            articles = queue.Queue()
            
            # Multi-threaded 
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS) as executorSearch:
                busySearch = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS) as executorPV:
                    busyPV = 0

                    prog = 0
                    populated = 0
                    errors = 0

                    future_requests = {}
                    while future_requests or not sps.empty() or not articles.empty():
                        if progress.wasCanceled():
                            break

                        # IF (a) there are still searchPhrases and (b) it has been PER seconds since RATE searches ago and
                        # (c) there is a thread ready to receive work: THEN give that thread work.
                        while not sps.empty() and time.time() > searchTimes[searchNo % RATE] + PER * 1.01 and busySearch < CONNECTIONS:
                            searchTimes[searchNo % RATE] = time.time()
                            searchNo += 1
                            busySearch += 1
                            sp, nid = sps.get()
                            future_requests[executorSearch.submit(_searchWiki,sp,ti=TIMEOUT)] = (executorSearch, nid)

                        done, _ = concurrent.futures.wait(
                                    future_requests, timeout=0.01,
                                    return_when=concurrent.futures.FIRST_COMPLETED)

                        for future in done:
                            prog += 1
                            progress.setValue(prog)
                            res = future.result()
                            exe, nid = future_requests[future]
                            if exe == executorSearch:
                                busySearch -= 1
                                if res is None or isinstance(res, requests.HTTPError):
                                    note = self.bmw.col.getNote(nid)
                                    if res is None:
                                        note[self.fDict[0]["useFieldName"].text()] = "ERROR: Wikipedia return no search results"
                                    else:
                                        note[self.fDict[0]["useFieldName"].text()] = "ERROR: HTTP Error while searching for article"
                                    self.bmw.col.update_note(note)
                                    errors += 1
                                    prog += 1
                                    progress.setValue(prog)
                                else:
                                    articles.put((res,nid))
                            if exe == executorPV:
                                busyPV -= 1
                                note = self.bmw.col.getNote(nid)
                                if isinstance(res, requests.HTTPError):
                                    note[self.fDict[0]["useFieldName"].text()] = "HTTP Error while querying pageviews"
                                    errors += 1
                                else:
                                    note[self.fDict[0]["useFieldName"].text()] = str(res)
                                    populated += 1
                                self.bmw.col.update_note(note)
                            del future_requests[future]
                            
                        # Same as top paragraph of loop
                        while not articles.empty() and time.time() > pVTimes[pVNo % RATE] + PER * 1.01 and busyPV < CONNECTIONS:
                            pVTimes[pVNo % RATE] = time.time()
                            pVNo += 1
                            busyPV += 1
                            article, nid = articles.get()
                            future_requests[executorPV.submit(_getPageviews,article,ti=TIMEOUT)] = (executorPV, nid)

            msg = "Added Pageview data for {} out of {} selected notes. {} errors".format(populated,len(self.nids),errors)
            showInfo(msg, textFormat="rich", parent=self)

        self.close()

    def _setupUi(self) -> None:
        """
        Sets up the UI for the Add Fame dialog.
        """

        def _insertField(i: int) -> None:
            """
            Inserts the selected field wrapped in "{{ }}" to act as a merge tag.

            :param i: An int, the index of the field selected.
            """

            if self.fDict[i]["insertSelect"].currentIndex() != 0:
                self.fDict[i]["edit"].insertPlainText("{{"+self.fDict[i]["insertSelect"].currentText()+"}}")
                self.fDict[i]["insertSelect"].setCurrentIndex(0)
            self.fDict[i]["edit"].setFocus()

        def _updateExample(i: int) -> None:
            """
            Generate and update the "Example" string under the textbox by merging with merge tags.

            :param i: 0 = Wiki, 1 = Google
            """

            mergeString = self.fDict[i]["edit"].toPlainText()
            note = mw.col.get_note(self.nid)
            msg = "<b>Example:</b> " + self._mergeFieldIntoTag(mergeString, note)
            self.fDict[i]["example"].setTextFormat(Qt.RichText)
            self.fDict[i]["example"].setText(msg)
        
        main_vbox = QVBoxLayout()
        if True:
            ivbox = QVBoxLayout()
            desc_msg = "Add fields containing the number of Wikipedia pageviews "
            desc_msg+= "for an article (the first that Wikipedia search returns) and/or "
            desc_msg+= "the number of Google hits for a search term.  Note: ensure no field begins with '{'."
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
                if True:
                    fd["vbox"] = QVBoxLayout()
                    if True:
                        fd["insertField"] = QFormLayout()
                        if True:
                            fd["insertSelect"] = QComboBox()
                            fd["insertSelect"].addItems(["SELECT FIELD"] + self.fields)
                            fd["insertSelect"].currentIndexChanged.connect(lambda _, x = i: _insertField(x))
                        fd["insertField"].addRow(QLabel("Insert field:"), fd["insertSelect"])
                        fd["edit"] = QPlainTextEdit()
                        fd["example"] = QLabel("<b>Example:</b> ")
                        fd["example"].setWordWrap(True)
                        fd["useField"] = QFormLayout()
                        if True:
                            fd["useFieldName"] = QLineEdit()
                            fd["useFieldName"].setText(fd["newFieldPlaceholder"])
                            #fd["useFieldName"].currentIndexChanged.connect(lambda _, x = i: _insertField(x))
                        fd["useField"].addRow(QLabel("Add Fame into Field:"), fd["useFieldName"])
                    fd["vbox"].addLayout(fd["insertField"])
                    fd["vbox"].addWidget(fd["edit"])
                    fd["vbox"].addWidget(fd["example"])
                    fd["vbox"].addLayout(fd["useField"])
                fd["gb"].setLayout(fd["vbox"])
                fd["edit"].textChanged.connect(lambda x = i: _updateExample(x))

            buttonBox = QDialogButtonBox(Qt.Horizontal, self)
            doneButton = buttonBox.addButton(QDialogButtonBox.StandardButton.Ok)
            cancelButton = buttonBox.addButton(QDialogButtonBox.StandardButton.Cancel)
            helpButton = buttonBox.addButton(QDialogButtonBox.StandardButton.Help)
            doneButton.setToolTip("Begin adding fame...")
            doneButton.clicked.connect(lambda _: self.accept())
            cancelButton.clicked.connect(self.reject)

        main_vbox.addLayout(ivbox)
        main_vbox.addWidget(self.fDict[0]["gb"])
        main_vbox.addWidget(self.fDict[1]["gb"])
        main_vbox.addWidget(buttonBox)

        self.setLayout(main_vbox)
        self.fDict[0]["edit"].setFocus()
        self.setMinimumWidth(540)
        self.setMinimumHeight(550)
        self.resize(540,550)
        self.setWindowTitle("Add Fame...")


def addFame(browser) -> None:
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    dialog = AddFameDialog(browser, nids)
    dialog.exec_()

def orderNotes(browser) -> None:
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    tooltip("Selected! (To be developed)")
    # dialog = AddFameDialog(browser, nids)
    # dialog.exec_()

def setupMenu(browser : QMainWindow) -> None:
    menu = browser.form.menu_Notes
    menu.addSeparator()

    # Setup a new menu item, "Add Fame..."
    addFameAction = QAction("Add Fame...", mw)
    menu.addAction(addFameAction)
    qconnect(addFameAction.triggered, lambda: addFame(browser))

    # Setup a new menu item, "Order Notes..."
    addFameAction = QAction("Order Notes by...", mw)
    menu.addAction(addFameAction)
    qconnect(addFameAction.triggered, lambda: orderNotes(browser))

gui_hooks.browser_menus_did_init.append(setupMenu)

