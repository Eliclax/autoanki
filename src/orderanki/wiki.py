from copy import deepcopy
import json
import os
import requests
from typing import Union, Dict, List, Optional
from urllib import parse
from urllib.parse import unquote
from time import sleep

# If running this module by itself for dev purposes, you can change the verbosity by changing the "v: int = 1" line
verbose: int = 0
v: int = 1

headers = {'User-Agent': 'AutoankiBot/0.1 (https://github.com/Eliclax/autoanki; tw2000x@gmail.com)'}

if __name__ == "__main__":
    verbose = v
else:
    class Wikifame:
        """
        The class representing the data structure containing all Anki and Wikipedia data
        """

        from anki.notes import Note, NoteId
        from aqt import AnkiQt

        def __init__(
            self,
            mw: Optional[AnkiQt],
            nid: Optional[NoteId] = None,
            note: Optional[Note] = None,
            search_phrase: Optional[str] = None,
            pageviews_field_name: Optional[str] = None,
            pageviews: Optional[int] = None,
            article_field_name: Optional[str] = None,
            article: Optional[str] = None,
            article_fixed_field_name: Optional[str] = None,
            article_fixed: Optional[str] = None,
            desc_field_name: Optional[str] = None,
            desc: Optional[str] = None,
            project: Optional[str] = None,
            ) -> None:
            """
            Must contain search_phrase or article
            """

            assert search_phrase or article

            self.mw = mw
            self.nid = nid
            self.note = note
            if self.note is None and self.nid is not None:
                self.note = self.mw.col.get_note(self.nid)
            self.search_phrase = search_phrase
            self.project = project
            self.fields: Dict = {}
            self.fields["article"] = article
            self.fields["article_fixed"] = article_fixed
            self.fields["desc"] = desc
            self.fields["pageviews"] = pageviews
            self.field_names: Dict = {}
            self.field_names["article"] = article_field_name
            self.field_names["article_fixed"] = article_fixed_field_name
            self.field_names["desc"] = desc_field_name
            self.field_names["pageviews"] = pageviews_field_name

        def set(self, field: str, value: Optional[Union[str, int]]) -> None:
            """
            Sets the python field and the Anki field to be equal to value.

            :param field: The name of the field, must be one of: article, article_fixed, desc, pageviews
            :param value: The value to set the field as
            """

            self.fields[field] = value
            if self.field_names[field] is not None:
                if value is None:
                    self.note[self.field_names[field]] = ""
                else:
                    self.note[self.field_names[field]] = str(value)
            self.mw.col.update_note(self.note)

        def search_up_article(self, timeout: float = 5) -> 'Wikifame':
            """
            If self.search_phrase is populated, this populates "article" and "article_fixed"
            """

            if self.search_phrase is None:
                self.set("article","ERROR: No Search Phrase")
                self.set("article_fixed","ERROR: No Search Phrase")
                raise Exception
            try:
                article = search_article_url(self.search_phrase, timeout)
                self.set("article",article)
                self.set("article_fixed",article)
            except requests.HTTPError:
                self.set("article","ERROR: HTTP Error")
                self.set("article_fixed","ERROR: HTTP Error")
                raise
            return self

        def fill_pageviews(self, timeout: float = 5) -> 'Wikifame':
            """
            If "article" is populated, this populates "pageviews"
            """

            try:
                pageviews = get_pageviews(self.fields["article"], self.project, timeout=timeout)
                self.set("pageviews",pageviews)
            except requests.HTTPError:
                self.set("pageviews","ERROR: HTTP Error")
                raise
            return self

        def fill_description(self, timeout: float = 5) -> 'Wikifame':
            """
            If "article" is populated, this populates "description"
            """

            # if self.fields["article"] is None:
            #     self.search_up_article(timeout=timeout)
            try:
                desc = get_desc1(self.fields["article"], timeout=timeout)
                self.set("desc", desc)
            except requests.HTTPError:
                self.set("desc", "ERROR: HTTP Error")
                raise
            return self

def search_article_url(search_phrase: str, timeout: float = 5) -> Optional[str]:
    """
    Given a search phrase, returns the top result after Searching en.wikipedia.org

    :param search_phrase: The search phrase that you want to search en.wikipedia.org with.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The title of the article, as a URL string.
    """

    search_url = "https://en.wikipedia.org/w/api.php?action=opensearch&search="
    search_url += parse.quote(search_phrase)
    search_url += "&limit=10&namespace=0&format=json"
    try:
        resp = requests.get(search_url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError:
        raise
    try:
        contents: str = resp.json()
        article = os.path.basename(parse.urlparse(contents[3][0]).path)
    except:
        article = None
    if verbose >= 1:
        print("   > Searched: {} -> {}".format(search_phrase, article))
    return article

def get_pageviews(
    article: Optional[str], 
    project: str = "en.wikipedia.org",
    access: str = "all-access",
    agent: str = "user",
    granularity: str = "monthly",
    start: str = "20150701",
    end: str = "20230101",
    timeout: float = 5
    ) -> int:
    """
    Gets the Wikipedia pageviews over a timeframe, given a URL-encoded Wikipedia article title. If empty, returns 0. See https://wikimedia.org/api/rest_v1/#

    :param article: The title of any article in the specified project. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param project: If you want to filter by project, use the domain of any Wikimedia project, for example 'en.wikipedia.org', 'www.mediawiki.org' or 'commons.wikimedia.org'.
    :param access: If you want to filter by access method, use one of desktop, mobile-app or mobile-web. If you are interested in pageviews regardless of access method, use all-access. Available values : all-access, desktop, mobile-app, mobile-web
    :param agent: If you want to filter by agent type, use one of user, automated or spider. If you are interested in pageviews regardless of agent type, use all-agents. Available values : all-agents, user, spider, automated
    :param granularity: The time unit for the response data. As of today, the only supported granularity for this endpoint is daily and monthly. Available values : daily, monthly
    :param start: The date of the first day to include, in YYYYMMDD or YYYYMMDDHH format
    :param end: The date of the last day to include, in YYYYMMDD or YYYYMMDDHH format
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The number of pageviews
    """

    if article is None:
        return 0

    pageviews = 0
    if article != "":
        wiki_url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        wiki_url += "{}/{}/{}/{}/{}/{}/{}".format(project, access, agent, article, granularity, start, end)
        try:
            resp = requests.get(wiki_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            raise
        contents: str = resp.json()
        if verbose >= 2:
            print(json.dumps(contents, indent=4))
        for item in contents["items"]:
            pageviews += item["views"]
    if verbose >= 1:
        print("   > Queried: {:14d} | {}".format(pageviews, article))
    return pageviews

def get_desc1(article: Optional[str], timeout: float = 5) -> str:
    """
    Given a single article titles, returns a single short descriptions.
    
    :param article: The title of any article in en.wikipedia.org. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The list of short descriptions
    """

    search_url = "https://en.wikipedia.org/w/api.php?format=json&action=query&prop=description&titles={}".format(article)
    try:
        resp = requests.get(search_url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError:
        raise
    try:
        contents: str = resp.json()
        for page in contents["query"]["pages"]:
            desc = contents["query"]["pages"][page]["description"]
    except:
        desc = "ERROR: No short description found."
    if verbose >= 1:
        print("   > Desc: {} -> {}".format(article, desc))
    return desc


def get_desc(articles: List[Optional[str]] = [], timeout: float = 5) -> List[str]:
    """
    Given a list of article titles, returns a list of short descriptions. (Makes ceil(n/50) queries to Wikipedia.)
    
    :param articles: The list of titles of any article in the specified project. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The list of short descriptions
    """

    descs: List[str] = [""] * len(articles)

    for i in range(0, len(articles), 50):
        l = min(50, len(articles)-i)
        url = "https://en.wikipedia.org/w/api.php?format=json&action=query&prop=description&titles="
        url += '|'.join([a for a in articles[i:i+l] if a is not None])
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.HTTPError:
            raise
        contents: json = resp.json()
        normed: List[str] = deepcopy(articles[i:i+l])

        for j in range(len(normed)):
            normed[j] = unquote(normed[j])

        try:
            if verbose >= 1:
                print(contents["query"]["normalized"])
                print(normed)
            for j in range(len(normed)):
                for norm in contents["query"]["normalized"]:
                    if normed[j] == norm["from"]:
                        normed[j] = norm["to"]
        except KeyError:
            if verbose >= 1:
                print("Encountered KeyError")
            pass

        for j in range(l):
            for page in contents["query"]["pages"]:
                if normed[j] == contents["query"]["pages"][page]["title"]:
                    try:
                        descs[i+j] = contents["query"]["pages"][page]["description"]
                    except:
                        descs[i+j] = "ERROR: No short description found."
    if verbose >= 1:
        for i in range(len(articles)):
            print("   > Got description: {} | {} | {}".format(articles[i], normed[i], descs[i]))
    return descs

if __name__ == "__main__":
    get_pageviews("Noodle")
    get_pageviews("")
    get_pageviews("Donald_Trump")
    search_article_url("Noodles")
    get_pageviews(search_article_url("Stoke on Trent"))
    get_desc1("Apple")
    get_desc(["A","B","ILEUFLIDWUF","D","are_You_the_One%3F","Joe_Biden","WLIEHUFDWLIUHF"])