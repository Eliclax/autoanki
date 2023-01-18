from copy import deepcopy
import json
import os
from importlib_metadata import re
import requests
from typing import Union, Dict, List, Optional
from urllib import parse
from urllib.parse import unquote

# If running this module by itself for dev purposes, you can change the verbosity by changing the "v: int = 1" line
v: int = 1

def printv(ver: int = 0, *args, **kwargs) -> None:
    """
    A wrapper function for printing for different verbostiies

    :param ver: The minimum verbosity to print at
    """

    if verbose >= ver:
        print(*args, **kwargs)

verbose: int = 1
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
        from aqt.utils import showCritical

        class WikipediaError(Exception):
            """Generic error for ones returned by Wikipedia API"""
            def __init__(self, error: str = "", url: str = "", message: str = "Wikipedia Query Error"):
                self.error = error
                self.message = message
                self.url = url
                try:
                    self.dump = json.dump(error,indent=4)
                except:
                    self.dump = error
                super().__init__(f"{self.message}\n\nERROR: {self.dump}\n\nURL: {self.url}")

        class NoArticlesFound(WikipediaError):
            """An exception indicating that no article was found via Wiki search."""

        def __init__(
            self,
            mw: Optional[AnkiQt],
            nid: Optional[NoteId] = None,
            note: Optional[Note] = None,
            search_phrase: Optional[str] = None,
            project: Optional[str] = None,
            article: Optional[str] = None,
            desc: Optional[str] = None,
            pageviews: Optional[int] = None,
            article_field_name: Optional[str] = None,
            desc_field_name: Optional[str] = None,
            pageviews_field_name: Optional[str] = None,
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
            self.fields: Dict[str,str] = {}
            self.fields["article"] = article
            self.fields["desc"] = desc
            self.fields["pageviews"] = pageviews
            self.field_names: Dict[str,str] = {}
            self.field_names["article"] = article_field_name
            self.field_names["desc"] = desc_field_name
            self.field_names["pageviews"] = pageviews_field_name

        def set(self, field: str, value: Optional[Union[str, int]]) -> None:
            """
            Sets the python field and the Anki field to be equal to value.

            :param field: The name of the field, must be one of: article, desc, pageviews
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
            If self.search_phrase is populated, this populates "article"
            """

            if self.search_phrase is None:
                self.set("article","ERROR: No Search Phrase")
                raise Exception
            try:
                article = search_article_url(self.search_phrase, timeout)
                if article is None:
                    self.set("article","ERROR: No Articles Found")
                    raise Wikifame.NoArticlesFound
                self.set("article",article)
            except requests.HTTPError:
                self.set("article","ERROR: HTTP Error")
                raise
            except Wikifame.NoArticlesFound:
                raise
            return self

        def fill_pageviews(self, timeout: float = 5) -> 'Wikifame':
            """
            If "article" is populated, this populates "pageviews"
            """

            rem = re.search(r"(\|[^\|\n]*)$|([^\|\n]+)$",self.fields["article"])
            if rem is None:
                article = self.fields["article"][rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
                return self
            article = self.fields["article"][rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
            try:
                pageviews = get_pageviews(article, self.project, timeout=timeout)
            except requests.HTTPError:
                self.set("pageviews","ERROR: HTTP Error")
                raise
            self.set("pageviews",pageviews)
            return self

        def fill_description(self, timeout: float = 5) -> 'Wikifame':
            """
            If "article" is populated, this populates "description"
            """

            # if self.fields["article"] is None:
            #     self.search_up_article(timeout=timeout)

            rem = re.search(r"(\|[^\|\n]*)$|([^\|\n]+)$",self.fields["article"])
            if rem is None:
                return self
            article = self.fields["article"][rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
            try:
                desc = get_desc([article], timeout=timeout)[0]
            except requests.HTTPError:
                self.set("desc","ERROR: HTTP Error")
                raise
            self.set("desc",desc)
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
    printv(1, "   > Searched: {} -> {}".format(search_phrase, article))
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

    article = article.replace("|","").replace(" ","")
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
        printv(3, json.dumps(contents, indent=4))
        for item in contents["items"]:
            pageviews += item["views"]
        printv(1, "   > Queried: {:14d} | {}".format(pageviews, article))
    return pageviews


def get_desc(articles: List[str] = [], project: str = "en.wikipedia.org", timeout: float = 5) -> List[str]:
    """
    Given a list of article titles, returns a list of short descriptions, respectively. (Makes ceil(n/50) queries to Wikipedia.)
    
    :param articles: The list of titles of any article in the specified project. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The list of short descriptions
    """

    MAX_TITLES = 50
    descs: List[str] = [""] * len(articles)

    if len(articles) > MAX_TITLES:
        printv(1, f"Warning: Making {len(articles)//MAX_TITLES} unthrottled queries for short descriptions.")

    for i in range(0, len(articles), MAX_TITLES):
        l = min(MAX_TITLES, len(articles)-i)
        url = "https://{}/w/api.php?format=json&action=query&prop=description&redirects&".format(project)
        url += "titles=" + '|'.join(articles[i:i+l])
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            raise
        contents: json = resp.json()        
        redir: List[str] = [unquote(arti) for arti in articles[i:i+l]]

        if "query" in contents:
            if "normalized" in contents["query"]:
                for norm in contents["query"]["normalized"]:
                    for j in range(len(redir)):
                        if redir[j] == norm["from"]:
                            redir[j] = norm["to"]
            if "redirects" in contents["query"]:
                for norm in contents["query"]["redirects"]:
                    for j in range(len(redir)):
                        if redir[j] == norm["from"]:
                            redir[j] = norm["to"]
            if "pages" in contents["query"]:
                for j in range(l):
                    for page in contents["query"]["pages"]:
                        if redir[j] == contents["query"]["pages"][page]["title"]:
                            if "invalid" in contents["query"]["pages"][page]:
                                descs[i+j] = "ERROR: "+contents["query"]["pages"][page]["invalidreason"]
                            elif "missing" in contents["query"]["pages"][page]:
                                descs[i+j] = "ERROR: \""+contents["query"]["pages"][page]["title"]+"\" missing."
                            else:
                                descs[i+j] = contents["query"]["pages"][page]["description"]
                    if descs[i+j] == "":
                        descs[i+j] = "ERROR: Page not found in response"
        else:
            raise Wikifame.WikipediaError(contents["error"],url)

    if verbose >= 1:
        for i in range(len(articles)):
            printv(1, "   > Got description: {} | {} | {}".format(articles[i], redir[i], descs[i]))
    return descs

if __name__ == "__main__":
    get_pageviews("Noodle")
    get_pageviews("")
    get_pageviews("Donald_Trump")
    search_article_url("Noodles")
    get_pageviews(search_article_url("Stoke on Trent"))
    get_desc(["Apple"])[0]
    get_desc(["A","9_(number)","ILEUFLIDWUF","D","are_You_the_One%3F","Joe_Biden","WLIEHFW","6_{number)"])