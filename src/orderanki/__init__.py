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
        self._setupUi()
        if len(self.nids) == 1:
            msg = "<b>Adding Wikipedia fame to a single note</b><br><br>You have selected a single note.  Due to a weird bug I can't figure out, adding "
            msg+= "Wikipedia fame data when selecting a single note will result in incomplete data. "
            msg+= "This shouldn't pose any risk of messing up your deck, though."
            showWarning(msg,parent=self,textFormat="rich")
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
            sleep(0.2) # The previous command requires time to propagate its changes

        # Add wikipedia fame?
        if self.fDict[0]["gb"].isChecked():
            # Check if we have a connection to Wikipedia.
            try:
                wiki.search_article_url("Noodles")
            except error.URLError as err:
                self._handleNetworkError(err)
                return

            CONNECTIONS = 100
            RATE = 100
            PER = 1
            TIMEOUT = 5
            MAX_TITLES = 10

            # Setup Progress Dialog
            progress = QProgressDialog("Adding Wikipedia Pageviews...", "Stop", 0, len(self.nids)*2-len(self.nids)//-MAX_TITLES, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setMinimumSize(300,30)

            # Add necessary fields
            fieldName = self.fDict[0]["useFieldName"].text()
            _addField(fieldName)
            _addField(fieldName + " (URL)")
            _addField(fieldName + " (Description)")
            _addField(fieldName + " (URL fixed)")

            searchTimes = [-2*PER] * RATE
            pVTimes = [-2*PER] * RATE
            descTimes = [-2*PER] * RATE
            searchNo = 0
            pVNo = 0
            descNo = 0

            sps: queue.Queue[wiki.Wikifame] = queue.Queue()
            mergeString = self.fDict[0]["edit"].toPlainText()
            for nid in self.nids:
                search_phrase = self._mergeFieldIntoTag(mergeString,self.bmw.col.get_note(nid))
                wf = wiki.Wikifame(self.bmw,nid,search_phrase=search_phrase)
                wf.field_names["pageviews"] = self.fDict[0]["useFieldName"].text()
                wf.field_names["article"] = self.fDict[0]["useFieldName"].text() + " (URL)"
                wf.field_names["article_fixed"] = self.fDict[0]["useFieldName"].text() + " (URL fixed)"
                wf.field_names["desc"] = self.fDict[0]["useFieldName"].text() + " (Description)"
                wf.project = "en.wikipedia.org"
                sps.put(wf)

            q_for_pageviews: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_desc: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_PV_ints: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_article_strs: queue.Queue[wiki.Wikifame] = queue.Queue()
            q_for_desc_strs: queue.Queue[wiki.Wikifame] = queue.Queue()
            #list_for_desc: List[wiki.Wikifame] = []
            
            # Multi-threaded query loop initialisation
            executorSearch = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            executorPV = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            executorDesc = concurrent.futures.ThreadPoolExecutor(max_workers=CONNECTIONS)
            busySearch = 0
            busyPV = 0
            busyDesc = 0
            countDesc = 0
            
            prog = 0
            populated = 0
            errors = 0
            future_requests = {}
            descStrs = []

            # Multi-threaded query loop
            while future_requests or not sps.empty() or not q_for_pageviews.empty() or not q_for_desc.empty():# or countDesc < len(self.nids):
                if progress.wasCanceled():
                    break

                # IF (a) there are still searchPhrases and (b) it has been PER seconds since RATE searches ago and
                # (c) there is a thread ready to receive work: THEN give that thread work.
                while not sps.empty() and time.time() > searchTimes[searchNo % RATE] + PER * 1.01 and busySearch < CONNECTIONS:
                    searchTimes[searchNo % RATE] = time.time()
                    searchNo += 1
                    busySearch += 1
                    sp = sps.get()
                    future_requests[executorSearch.submit(wiki.Wikifame.search_up_article,sp,timeout=TIMEOUT)] = (executorSearch, [sp])

                done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

                for future in done:
                    res: Optional[Union[wiki.Wikifame, List[str]]] = future.result()
                    exe, listWfs = future_requests[future]
                    if exe == executorSearch:
                        busySearch -= 1
                        if res is None or isinstance(res, requests.HTTPError):
                            errors += 1
                            prog += 1
                            progress.setValue(prog)
                        else:
                            q_for_pageviews.put(res)
                            q_for_desc.put(res)
                            q_for_article_strs.put(res)
                            #list_for_desc.append(res)
                    elif exe == executorPV:
                        busyPV -= 1
                        # note = self.bmw.col.get_note(nid)
                        # self.bmw.col.update_note(note)
                        if isinstance(res, requests.HTTPError):
                            errors += 1
                        else:
                            populated += 1
                        q_for_PV_ints.put(res)
                    elif exe == executorDesc:
                        busyDesc -= 1
                        q_for_desc_strs.put(res)
                        # note = self.bmw.col.get_note(nid)
                        # self.bmw.col.update_note(note)
                        # print(res)
                        # for j in range(len(res)):
                        #     wfss: wiki.Wikifame = listWfs[j]
                        #     wfss.fields["desc"] = res[j]
                        #     wfss.note[wfss.field_names["desc"]] = str(res[j])
                        #     self.bmw.col.update_note(wfss.note)
                        #     print(wfss.field_names["desc"])
                        #     print("2: "  +self.bmw.col.get_note(wfss.nid)[wfss.field_names["desc"]])
                        #     print("2.1: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

                    prog += 1
                    progress.setValue(prog)
                    del future_requests[future]
                    
                # Same as top paragraph of loop for actual pageviews
                while not q_for_pageviews.empty() and time.time() > pVTimes[pVNo % RATE] + PER * 1.01 and busyPV < CONNECTIONS:
                    pVTimes[pVNo % RATE] = time.time()
                    pVNo += 1
                    busyPV += 1
                    wf = q_for_pageviews.get()
                    future_requests[executorPV.submit(wiki.Wikifame.fill_pageviews,wf,timeout=TIMEOUT)] = (executorPV, [wf])

                # Same as top paragraph of loop for actual pageviews
                while not q_for_desc.empty() and time.time() > descTimes[descNo % RATE] + PER * 1.01 and busyDesc < CONNECTIONS:
                    descTimes[descNo % RATE] = time.time()
                    descNo += 1
                    busyDesc += 1
                    wf = q_for_desc.get()
                    future_requests[executorDesc.submit(wiki.Wikifame.fill_description,wf,timeout=TIMEOUT)] = (executorDesc, [wf])


                # def b1() -> bool: return countDesc + MAX_TITLES < len(list_for_desc)
                # def b2() -> bool: return not future_requests and sps.empty() and q_for_pageviews.empty() and countDesc < len(self.nids)
                # while (b1() or b2()) and time.time() > descTimes[descNo % RATE] + PER * 1.01 and busyDesc < CONNECTIONS:
                #     descTimes[descNo % RATE] = time.time()
                #     descNo += 1
                #     busyDesc += 1
                #     k = countDesc
                #     l = min(MAX_TITLES, len(list_for_desc)-k)
                #     for j in range(countDesc, len(list_for_desc)):
                #         descStrs.append(list_for_desc[j].fields["article"])
                #     future_requests[executorDesc.submit(wiki.get_desc,descStrs[k:k+l],timeout=TIMEOUT)] = (executorDesc, list_for_desc[k:k+l])
                #     countDesc += l

            sleep(1)

            # Multi-threaded query loop clean-up
            executorSearch.shutdown(wait = False, cancel_futures = True)
            executorPV.shutdown(wait = False, cancel_futures = True)
            executorDesc.shutdown(wait = False, cancel_futures = True)

            # print(cleanedWfs)
            # print(cleanedStrs)

            # i = 0
            # while i < len(list_for_desc) or future_requests:
            #     while i < len(list_for_desc) and time.time() > descTimes[descNo % RATE] + PER * 1.01 and busyDesc < CONNECTIONS:
            #         print("Entering Loop A")
            #         descTimes[descNo % RATE] = time.time()
            #         descNo += 1
            #         busyDesc += 1
            #         l = min(MAX_TITLES, len(list_for_desc)-i)
            #         future_requests[executorDesc.submit(wiki.get_desc,cleanedStrs[i:i+l],timeout=TIMEOUT)] = cleanedWfs[i:i+l]
            #         i += MAX_TITLES

            #     done, _ = concurrent.futures.wait(future_requests, timeout=0.01, return_when=concurrent.futures.FIRST_COMPLETED)

            #     for future in done:
            #         print("Entering B")
            #         busyDesc -= 1
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
            # #executorDesc.shutdown(wait = False)
            # print("2.4: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

            progress.setValue(progress.maximum())

            msg = "Added Pageview data for {} out of {} selected notes. {} errors".format(populated,len(self.nids),errors)
            print("2.5: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
            print("2.5: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])
            showInfo(msg, textFormat="rich", parent=self)
            print("2.6: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
            print("2.6: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

            for nid in self.nids:
                search_phrase = self._mergeFieldIntoTag(mergeString,self.bmw.col.get_note(nid))
                wf = wiki.Wikifame(self.bmw,nid,search_phrase=search_phrase)
                wf.field_names["pageviews"] = self.fDict[0]["useFieldName"].text()
                wf.field_names["article"] = self.fDict[0]["useFieldName"].text() + " (URL)"
                wf.field_names["article_fixed"] = self.fDict[0]["useFieldName"].text() + " (URL fixed)"
                wf.field_names["desc"] = self.fDict[0]["useFieldName"].text() + " (Description)"
                wf.project = "en.wikipedia.org"
                sps.put(wf)

            wf = sps.get()
            # print("2.65: "+wf.fields["pageviews"])
            # print("2.65: "+wf.fields["desc"])

        # while not q_for_article_strs.empty():
        #     wf = q_for_article_strs.get()
        #     print("wf.field_names[\"article\"]: " + wf.field_names["article"])
        #     print("str(wf.fields[\"article\"]): " + str(wf.fields["article"]))
        #     wf.note[wf.field_names["article"]] = str(wf.fields["article"])
        #     wf.mw.col.update_note(wf.note)

        # while not q_for_PV_ints.empty():
        #     wf = q_for_PV_ints.get()
        #     print("wf.field_names[\"pageviews\"]: " + wf.field_names["pageviews"])
        #     print("str(wf.fields[\"pageviews\"]): " + str(wf.fields["pageviews"]))
        #     wf.note[wf.field_names["pageviews"]] = str(wf.fields["pageviews"])
        #     wf.mw.col.update_note(wf.note)

        # while not q_for_desc_strs.empty():
        #     wf = q_for_desc_strs.get()
        #     print("wf.field_names[\"desc\"]: " + wf.field_names["desc"])
        #     print("str(wf.fields[\"desc\"]): " + str(wf.fields["desc"]))
        #     wf.note[wf.field_names["desc"]] = str(wf.fields["desc"])
        #     wf.mw.col.update_note(wf.note)

        self.close()

        print("2.7: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
        print("2.7: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

        self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"] = "HI!!"
        self.bmw.col.update_note(self.bmw.col.get_note(self.nids[0]))
        print("2.8: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews"])
        print("2.8: "+self.bmw.col.get_note(self.nids[0])["Wiki Pageviews (Description)"])

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
                            fd["insertSelect"].currentIndexChanged.connect(lambda _, x = i: _insertField(x))
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

