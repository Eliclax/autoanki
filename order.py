# STEPS
# 0. Take inputs                                         ✓
# 1. Extract <name>s from Anki deck                      ✓
# 2. Find Wikipedia <url>s for <name>s                   ✓
# 3. Query WMF READ DB to get <pageview>s                ✓
# 4. Get the Google <hitCount>s for <name>s              __
# 5. Update Anki deck and zip back into .akpg file       ✓

# TO-DO
# Write Add-on directly into Anki
# Customisation of "libreoffice --calc" part
# Implement custom search text specification for Google hits
# Allow modular usage (start -> end, start -> csv, csv -> end, etc.)

# ADD-ON IDEAS
# Functions:
#  • Notes -> add and populate Wikipedia URL field -> add and populate page views field
#  • Notes -> add and populate Google search term field -> add and populate Google hits field
#  • CSV, Notes -> Re-order deck according to CSV
#  • Notes, pageviews and/or google hits fields -> re-order deck

# RESOURCES
# https://github.com/ankidroid/Anki-Android/wiki/Database-Structure#notes
# https://cognoteo.blogspot.com/2021/11/anki-svgs.html
# https://pyformat.info
# https://wikimedia.org/api/rest_v1/#/Pageviews%20data/get_metrics_pageviews_per_article__project___access___agent___article___granularity___start___end_
# https://groups.google.com/g/google-ajax-search-api/c/GQI5coTTXG4?pli=1

# TERMINOLOGY:
# Model = Note type (it's called model in the Anki source code)
# Ident = Name of the "thing" to be searched on Wikipedia/Google

# IMPORTS
from argparse import ArgumentParser
import sqlite3
import zipfile
import json
import os
import re
import copy
import csv
import shutil
from urllib import request, parse
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

# INPUTS
apkg_path = ""
"""
absolute path to .apkg file, including ".apkg".  ".colpkg" not yet supported.
"""

identifiers = ""
"""
`identifiers` is a dictionary {model name: list of ident field names in order of 
check priority} and should really be called `ident_fields_names_in_model_name`
"""

# apkg_path = "test3.apkg"
# identifiers = {"Basic-2d749": ["Name",]}

# identifiers = {"UK Geog-57440": ["Location"], "Basic" : ["Front"], }

# apkg_path = "/home/eliclax/Documents/knowledge/anki/us-pres/US-Presidents.apkg"
# identifiers = {"US-Presidents": ["Name", "Real name"]}

start_date = "20150701"
end_date = "20220901"
get_wiki_pv = True
get_google_hits = False
max_rows = -1
verbosity_input = 10

# GLOBAL VARS
ident_fields_of_model = {} # model -> ident field
notes = []
"""
List of {"nid": note_id, "ident": ident_name, "fame": ...} dicts
"""

# FUNCTIONS
def parse_inputs():
    parser = ArgumentParser(description=
    """This program reorders the notes in an Anki deck by how well-known each note is.  It
    does this via checking Wikipedia article pageviews and/or Google search hits.  You need
    to tell this program which field of each note its "name" is in, as a JSON string (see -h for more).
    Note that determining the correct Wikipedia article and finding a representative Google
    search query can be quite difficult.""")
    parser.add_argument("-s", "--start", dest="start_date", default="20150701",
                        help="the starting date for wikipedia view data. format YYYYMMDD")
    parser.add_argument("-e", "--end", dest="end_date", default="20220901",
                        help="the ending date for wikipedia view data. format YYYYMMDD")
    parser.add_argument("-v", "--verbosity", dest="verbosity_input", default=10,
                        help="set output verbosity. 0 is silent, 10 is default, 100 is max.")
    parser.add_argument("-m", "--max", dest="max_rows", default=-1,
                        help="set max number of rows. -1 means no limit. useful when debugging.")

    parser.add_argument("path", help="path to the .apkg file")
    parser.add_argument("identifiers", help=
    """Input a JSON string indicating, for each note type, a list of fields to grab the identity from.  For example,
    a deck about US History might contain a note type for Presidents and a note type for Periods.  If you want
    to use the "name" field for both note types, then input
        {"Presidents": ["Name"], "Periods": ["Name"]}.
    However, suppose that the note on George Washington has {"Name": "", "Real name": "George Washintgon"} and the 
    note on Bill Clinton has {"Name": "Bill Clinton", "Real name": "William J. Clinton"} then neither
        {"Presidents": ["Name"], "Periods": ["Name"]}   nor   {"Presidents": ["Real Name"], "Periods": ["Name"]}
    will correctly get the desired information.  In this case, use 
        {"Presidents": ["Name", "Real name"], "Periods": ["Name"]}.
    This program will attempt to grab the "Name" for George Washington, but since it is empty, it
    will try grabbing the "Real name" field.  The program will keep going down the list of fields
    until a non-empty field is found for that note.""")

    args = parser.parse_args()

    global apkg_path, identifiers, start_date, end_date, verbosity_input, max_rows
    apkg_path = args.path
    identifiers = args.identifiers
    start_date = args.start_date
    end_date = args.end_date
    verbosity_input = args.verbosity_input
    max_rows = args.max_rows

def get_pageviews(url_bit: str = ""):
    pageviews = 0
    wiki_url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org"
    wiki_url += "/all-access/user/" + url_bit + "/monthly/" + start_date + "/" + end_date
    contents = json.loads(request.urlopen(wiki_url).read())
    #print(json.dumps(json.loads(contents), indent=4))
    for item in contents["items"]:
        pageviews += item["views"]
    #print(total_views)
    return pageviews

def go_get_wiki_pv(max = max_rows, verbosity = 0):
    if verbosity >= 10:
        print()
        print("GETTING WIKIPEDIA PAGEVIEWS...")
        print("  No   URL bit                    Pageviews")
    for i in range(max):
        # SEE https://stackoverflow.com/questions/27457977/searching-wikipedia-using-api
        wiki_search_url = "https://en.wikipedia.org/w/api.php?action=opensearch&search="
        wiki_search_url += notes[i]["ident"].replace(" ","+")
        wiki_search_url += "&limit=10&namespace=0&format=json"
        search_result = json.loads(request.urlopen(wiki_search_url).read())
        url_bit = os.path.basename(parse.urlparse(search_result[3][0]).path)
        notes[i]["url_bit"] = url_bit
        notes[i]["wiki_urls"] = copy.deepcopy(search_result[3])
        #print(url_bit)
        #print(json.dumps(contents, indent=4))

        # Determine Wikipedia page views from start_date to end_date
        notes[i]["pageviews"] = get_pageviews(url_bit)
        if verbosity >= 10:
            print('{:4d}'.format(i) + ":  " + '{:25.22}'.format(notes[i]["url_bit"]) + '{:>11.11}'.format(str(notes[i]["pageviews"])))

def re_get_wiki_pv(max = max_rows, verbosity = 0):
    with open(apkg_path + "_ordering/ordering.csv", newline='') as csvfile:
        csvreader = csv.reader(csvfile, delimiter="\t", quotechar='"')
        for row in csvreader:
            #print(row)
            if row[5] == "using":
                continue
            id = int(row[0])
            notes[id]["nid"] = row[1]
            notes[id]["ident"] = row[4]
            notes[id]["url_bit"] = row[6]
            if row[2] != '':
                notes[id]["pageviews"] = int(row[2])
            # if row[3] != '':
            #     notes[id]["googlehits"] = int(row[3])
            if int(row[5]) != 0:
                old_url = str(row[6])
                new_url = str(row[6+int(row[5])])
                msg = '{:18.15}'.format(notes[id]["ident"]) + " pv " + str(row[2])
                msg += " (" + old_url + ") -> "
                notes[id]["pageviews"] = get_pageviews(new_url)
                msg += str(notes[id]["pageviews"]) + " (" + new_url + ")"
                notes[id]["url_bit"] = new_url
                print(msg)

def go_get_google_hits(max = max_rows, verbosity = 0):
    if verbosity >= 10:
        print("GOOGLE HITS")
        print("  No   URL bit                        Google hits")
    caps = DesiredCapabilities().FIREFOX
    caps["pageLoadStrategy"] = "none"  #  interactive
    driver = webdriver.Firefox(capabilities=caps)
    driver.get("https://www.google.com")
    button = WebDriverWait(driver, timeout=10).until(EC.element_to_be_clickable((By.ID, 'L2AGLb')))
    #driver.find_element_by_id('L2AGLb').click()
    button.click()
    for i in range(max):
        google_search_url = "https://www.google.com/search?q="
        google_search_url += notes[i]["ident"].replace(" ","+")
        driver.get(google_search_url)
        WebDriverWait(driver, poll_frequency=0.02, timeout=10).until(EC.invisibility_of_element_located((By.ID,"result-stats")))
        el = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID,"result-stats"))
        match = re.search(r"About (.*) results .*", el.text)
        #match = re.search(r"About (.*) results .*", driver.find_element_by_id('result-stats').text)
        #driver.execute_script("window.stop();")
        if match:
            hits = match.group(1).replace(",","")
            notes[i]["googlehits"] = int(hits)
        else:
            notes[i]["googlehits"] = -1
        if verbosity >= 10:
            print('{:4d}'.format(i) + ":  " + '{:25.22}'.format(notes[i]["ident"].replace(" ","+")) + '{:>11.11}'.format(str(notes[i]["googlehits"])))

def extract():
    with zipfile.ZipFile(apkg_path + "_ordered.apkg", 'r') as zip:
        zip.extractall(apkg_path + "_ordering/unzipped/")

def load_model(model_key = ""):
    """
    Loads model as list of dicts, each dict
    is {"nid": note_id, "flds": {note data as a dict}}

    :param model_key: The model_key for the model
    :return: List of dicts
    """

    with sqlite3.connect(apkg_path + "_ordering/unzipped/collection.anki2") as con1:
        cur1 = con1.cursor()
        model = json.loads(cur1.execute("SELECT models FROM col").fetchone()[0])[model_key]
        res = cur1.execute("SELECT id, flds FROM notes WHERE mid=(?)", (model_key,)).fetchall()
        lis = []
        for entry in res:
            flds = {}
            flds_values = entry[1].split("\x1f")
            for i in range(len(flds_values)):
                flds[model["flds"][i]["name"]] = flds_values[i]
            lis.append({"nid": entry[0], "flds": flds})
    return lis

def get_idents_from_db():
    # Build "ident_fields_of_model" dict {model key: list of ident field names}
    models = json.loads(cur.execute("SELECT models FROM col").fetchone()[0])
    for ident_key in identifiers.keys():
        model_found = False
        for model_key in models.keys():
            if models[model_key]["name"] == ident_key:
                model_found = True
                ident_fields_of_model[model_key] = identifiers[ident_key]
        if not model_found:
            msg = "ERROR: Model name \"" + ident_key + "\" not found.  Model names: ["
            for key in models.keys():
                msg += models[key]["name"] + ", "
            print(msg + "]")
            exit()

    # Check field names can be found in respective models
    for model_key in ident_fields_of_model.keys():
        for field in ident_fields_of_model[model_key]:
            field_no = 0
            flds = models[model_key]["flds"]
            while flds[field_no]["name"] != field:
                field_no += 1
                if field_no >= len(flds):
                    msg = "ERROR: Ident field \"" + field + "\" not found in "
                    msg += "fields of model \"" + models[model_key]["name"]
                    msg += "\" (" + model_key + ") = ["
                    for i in range(len(flds)):
                        msg += flds[i]["name"] + ", "
                    print(msg + "]")
                    exit()

    # Build "notes" (List of {note id: X, ident: X} dicts) from notes in each model
    notes_of_model = {}
    for model_key in ident_fields_of_model.keys():
        notes_of_model[model_key] = load_model(model_key)

    for model_key in ident_fields_of_model.keys():
        for note in notes_of_model[model_key]:
            ident = ""
            for i in range(len(ident_fields_of_model[model_key])):
                if note["flds"][ident_fields_of_model[model_key][i]] != "":
                    ident = note["flds"][ident_fields_of_model[model_key][i]]
                    break
                if i == len(ident_fields_of_model[model_key]) - 1:
                    print("warn1: some ident name is empty string")
            notes.append({"nid": note["nid"], "ident": ident})

        # for entry in res.fetchall():
        #     ident = entry[1].split("\x1f")[field_no].replace('<br>','').replace('<br/>','').replace('<br />','')
        #     notes.append({"nid": entry[0], "ident" : ident})
    
    if verbosity_input >= 20:
        for i in range(len(notes)):
            print('{:4d}'.format(i) + ": " + str(notes[i]))

def write_scout_to_csv(max = max_rows):
    with open(apkg_path + "_ordering/ordering.csv","w",newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        row = ["id","nid","pageviews","googlehits","ident","using",0,1,2,3,4,5,6,7,8,9]
        csvwriter.writerow(row)
        for i in range(max):
            row = [i]
            row += [str(notes[i]["nid"])]
            if get_wiki_pv:
                row += [str(notes[i]["pageviews"])]
            else:
                row += [""]
            if get_google_hits:
                row += [str(notes[i]["googlehits"])]
            else:
                row += [""]
            if get_wiki_pv:
                row += [notes[i]["ident"], 0]
                for j in range(len(notes[i]["wiki_urls"])):
                    row += [os.path.basename(parse.urlparse(notes[i]["wiki_urls"][j]).path)]
            csvwriter.writerow(row)

# START OF PROGRAM

parse_inputs()

# check path is valid
print(apkg_path)
if apkg_path[-5:] != ".apkg":
    print("Invalid file path: does not end with .apkg")
    exit()
else:
    apkg_path = apkg_path[:-5]
identifiers = json.loads(identifiers)

shutil.copy(apkg_path + ".apkg", apkg_path + "_ordered.apkg")
extract() # Extract APKG_PATH.apkg to folder APKG_PATH_ordering/unzipped/

with sqlite3.connect(apkg_path + "_ordering/unzipped/collection.anki2") as con:
    cur = con.cursor()
    get_idents_from_db() # Obtain idents from "notes" DB table

    if max_rows == -1:
        max_rows = len(notes)

    if get_wiki_pv:
        go_get_wiki_pv(max_rows, verbosity = verbosity_input)

    if get_google_hits:
        go_get_google_hits(max_rows, verbosity = verbosity_input)

    write_scout_to_csv(max_rows)
    exec = "libreoffice --calc \"" + apkg_path + "_ordering/ordering.csv\""
    os.system(exec)

    if get_wiki_pv:
        re_get_wiki_pv(max_rows, verbosity = verbosity_input)

    if get_google_hits:
        # TO CODE THIS
        pass

    # Set notes table "due" column
    sorted_notes = sorted(notes, key=lambda d: -d["pageviews"])
    for i in range(len(sorted_notes)):
        cur.execute("UPDATE cards SET due=(?) WHERE nid=(?)", (i, sorted_notes[i]["nid"]))
con.close()

# Zip apkg_name_ordered/unzipped
shutil.make_archive(apkg_path + "_ordered", 'zip', apkg_path + "_ordering/unzipped/")
os.rename(apkg_path + "_ordered.zip", apkg_path + "_ordered.apkg")

if verbosity_input >= 1:
    print("\nDone")