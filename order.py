# STEPS
# 0. Take inputs                                         __
# 1. Extract <name>s from Anki deck                      ✓
# 2. Find Wikipedia <url>s for <name>s                   ✓ ?
# 3. Query WMF READ DB to get <pageview>s                ✓
# 4. (Optional) Get the Google <hitCount>s for <name>s   ✓ ?
# 5. Update Anki deck and zip back into .akpg file       __

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
import sqlite3
import zipfile
import json
import os
import re
import copy
import csv
from urllib import request, parse
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

# INPUTS
apkg_name = "test3"
identifiers = {"Basic-2d749": "Name"}
#identifiers = {"UK Geog-57440": "Location", "Basic" : "Front", } # model name -> ident field
start_date = "20150701"
end_date = "20220901"
get_wiki_pv = True
get_google_hits = False
max_rows = -1

# GLOBAL VARS
field_of_model = {} # model -> ident field
notes = [] # List of {note id, ident, fame} dicts

# FUNCTIONS
def get_pageviews(url_bit = ""):
    pageviews = 0
    wiki_url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org"
    wiki_url += "/all-access/user/" + url_bit + "/monthly/" + start_date + "/" + end_date
    contents = json.loads(request.urlopen(wiki_url).read())
    #print(json.dumps(json.loads(contents), indent=4))
    for item in contents["items"]:
        pageviews += item["views"]
    #print(total_views)
    return pageviews

def go_get_wiki_pv(max = max_rows, verbose = False):
    if verbose:
        print("WIKIPEDIA PAGEVIEWS")
        print("  No   URL bit           Pageviews")
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
        if verbose:
            print('{:4d}'.format(i) + ":  " + '{:18.15}'.format(notes[i]["url_bit"]) + '{:>11.11}'.format(str(notes[i]["pageviews"])))

def go_get_google_hits(max = max_rows, verbose = False):
    if verbose:
        print("GOOGLE HITS")
        print("  No   URL bit           Google hits")
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
        if verbose:
            print('{:4d}'.format(i) + ":  " + '{:18.15}'.format(notes[i]["ident"].replace(" ","+")) + '{:>11.11}'.format(str(notes[i]["googlehits"])))

def get_database():
    archive = zipfile.ZipFile(apkg_name + ".apkg", 'r')
    col = archive.read('collection.anki2')
    with open(apkg_name + ".db","wb") as de:
        de.write(col)

def get_idents_from_db():
    # Build "field_of_model" (model -> ident field)
    res = cur.execute("SELECT models FROM col").fetchone()[0]
    models = json.loads(res)
    for ident_key in identifiers.keys():
        model_found = False
        for model_key in models.keys():
            if models[model_key]["name"] == ident_key:
                model_found = True
                field_of_model[model_key] = identifiers[ident_key]
        if not model_found:
            msg = "ERROR: Model name \"" + ident_key + "\" not found.  Model names: ["
            for key in models.keys():
                msg += models[key]["name"] + ", "
            print(msg + "]")
            exit()
    #print(field_of_model)

    # Build "notes" (List of {note id, ident, fame} dicts) from notes in each model
    for model_key in field_of_model.keys():

        # Find field number in model
        field_no = 0
        flds = models[model_key]["flds"]
        while flds[field_no]["name"] != field_of_model[model_key]:
            field_no += 1
            # If field_name not found, return error and exit
            if field_no >= len(flds):
                msg = "ERROR: Ident field \"" + field_of_model[model_key] + "\" not found in "
                msg += "fields of model \"" + models[model_key]["name"] + "\" (" + model_key + ") = ["
                for i in range(len(flds)):
                    msg += flds[i]["name"] + ", "
                print(msg + "]")
                exit()
        
        res = cur.execute("SELECT id, flds FROM notes WHERE mid=(?)", (model_key,))
        #print(res.fetchall())
        for entry in res.fetchall():
            ident = entry[1].split("\x1f")[field_no].replace('<br>','').replace('<br/>','').replace('<br />','')
            notes.append({"nid": entry[0], "ident" : ident})
    
    # for i in range(len(notes)):
    #     print('{:4d}'.format(i) + ": " + str(notes[i]))

def write_scout_to_csv(max = max_rows):
    with open(apkg_name + ".csv","w",newline='') as csvfile:
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
get_database() # Get database from .apkg file

with sqlite3.connect(apkg_name + ".db") as con:
    cur = con.cursor()
    get_idents_from_db() # Obtain idents from "notes" DB table

    if max_rows == -1:
        max_rows = len(notes)

    if get_wiki_pv:
        go_get_wiki_pv(max_rows, verbose = True)

    if get_google_hits:
        go_get_google_hits(max_rows, verbose = True)

    write_scout_to_csv(max_rows)
    os.system("libreoffice --calc \"" + apkg_name + ".csv\"")
    with open(apkg_name + ".csv", newline='') as csvfile:
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
            if row[3] != '':
                notes[id]["googlehits"] = int(row[3])
            if int(row[5]) != 0:
                old_url = str(row[6])
                new_url = str(row[6+int(row[5])])
                msg = '{:18.15}'.format(notes[id]["ident"]) + " pv " + str(row[2])
                msg += " (" + old_url + ") -> "
                notes[id]["pageviews"] = get_pageviews(new_url)
                msg += str(notes[id]["pageviews"]) + " (" + new_url + ")"
                notes[id]["url_bit"] = new_url
                print(msg)

    sorted_notes = sorted(notes, key=lambda d: -d["pageviews"])
    for i in range(len(sorted_notes)):
        cur.execute("UPDATE cards SET due=(?) WHERE nid=(?)", (i, sorted_notes[i]["nid"]))


con.close()

#os.remove(apkg_name + ".db")
print("\nDone")