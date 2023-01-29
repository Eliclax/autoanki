from ast import Str
from copy import deepcopy
import json
from optparse import Option
import os
from pickle import DEFAULT_PROTOCOL
from unittest.mock import DEFAULT
from importlib_metadata import re
import requests
from typing import Union, Dict, List, Optional
from urllib import parse

# If running this module by itself for dev purposes, you can change the verbosity by changing the "v: int = 1" line
v: int = 1
DEFAULT_LANG: str = "en"

def printv(ver: int = 0, *args, **kwargs) -> None:
    """
    A wrapper function for printing at different verbostiies

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
        The class representing the data structure containing all Anki and Wikipedia data.
        Each Wikifame object must be initialised with either an nid or a note, and either a search_phrase or an article.
        The default project is "en.wikipedia.org"
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

        # nid -> note [local]
        # merge_string -> search_phrase [local]
        # search_phrase --(language)-> Possible Articles [API:mediawiki.opensearch]
        # Possible Articles --(keywords)-> Final article URL, Description, No. of languages, Wikidata ID [API:wikidata.wbgetentities]
        # Final article -> Pageviews [API:REST-API]

        # nid
        # search_phrase
        # language_code
        # keywords

        # possible_articles

        # article
        # desc
        # num_of_langs
        # num_of_sitelinks
        # wikidata_id

        # pageviews


        def __init__(
            self,
            nid: Optional[NoteId] = None,
            search_phrase: Optional[str] = None,
            lang_code: str = DEFAULT_LANG,
            keywords: List[str] = [],

            possible_articles: Optional[List[str]] = None,

            article: Optional[str] = None,
            desc: Optional[str] = None,
            num_of_langs: Optional[int] = None,
            num_of_sitelinks: Optional[int] = None,
            wikidata_id: Optional[str] = None,

            pageviews: Optional[int] = None,
            ) -> None:
            """
            A Wikifame object.  It does not track any Anki information except for the nid, which is mostly for convenience.

            :param nid: The NoteId of the note. This is really only for convenience.
            :param search_phrase: The phrase to search using MediaWiki OpenSearch API
            :param lang_code: The language code to use throughout the process. {lang_code}.wikipedia.org should be valid.
            :param keywords: The keywords to look for in the short description of the articles that Opensearch returns.
            :param possible_articles: The top 10 articles that Opensearch returns.
            :param article: The entire URL of the known article
            :param desc: A short description of the item, as held by wikidata
            :param num_of_langs: The number of wikipedias in different languages with an entry
            :param num_of_sitelinks: The number of wikis with an entry, including e.g. wikivoyage
            :param wikidata_id: The ID of this object in wikidata
            :param pageviews: The number of pageviews over a period range.
            """

            self.nid = nid
            self.search_phrase = search_phrase
            self.lang_code = lang_code
            self.keywords = keywords

            self.possible_articles = possible_articles

            self.article = article
            self.desc = desc
            self.num_of_langs = num_of_langs
            self.num_of_sitelinks = num_of_sitelinks
            self.wikidata_id = wikidata_id

            self.pageviews = pageviews

            self.warning = False

        def fill_possible_articles(self, limit = 10, timeout: float = 5) -> 'Wikifame':
            """
            If self.search_phrase is populated, this populates self.possible_articles

            :param limit: The maximum number of search results to return.
            :param timeout: How many seconds to wait for the server to send data before giving up.
            :return: Itself, for convenience while threading
            """

            if self.search_phrase is None or self.search_phrase == "":
                printv(0, "ERROR: No Search Phrase")
                self.warning = True
                raise Exception("ERROR: No Search Phrase")
            try:
                self.possible_articles = search_possible_articles(search_phrase=self.search_phrase, limit=limit, lang_code=self.lang_code, timeout=timeout)
            except requests.HTTPError:
                self.warning = True
                raise
            if self.possible_articles == []:
                printv(0, f"ERROR: No Articles Found for {self.nid}")
                self.warning = True
                raise self.NoArticlesFound
            print(f"self.possible_articles is {self.possible_articles}")
            return self

        def wikidata_on_possible_articles(self, timeout: float = 5) -> 'Wikifame':
            """
            If self.possible_articles is populated, this function finds the correct self.article from keywords
            while also populating self's desc, num_of_langs, num_of_sites, and wikidata_id.

            :param timeout: How many seconds to wait for the server to send data before giving up.
            :return: Itself, for convenience while threading.
            """

            if self.possible_articles is None:
                try:
                    printv(0, "WARNING: No possible_articles, using search_phrase to get...")
                    self.fill_possible_articles()
                except Exception as err:
                    if err.args[0] == "ERROR: No Search Phrase":
                        raise

            titles = []
            for possible_article in self.possible_articles:
                titles.append(get_url_bit(possible_article))
            site = {f"{self.lang_code}wiki"}

            try:
                data = wikidata_wbgetentities(titles=titles, sites=site, timeout=timeout)
            except requests.HTTPError:
                self.warning = True
                raise

            if "entities" in data:
                entities: Dict[str, Optional[str]] = {}
                for article in self.possible_articles:
                    entities[article] = None
                    for entity in data["entities"]:
                        if "sitelinks" in data["entities"][entity]:
                            if article == data["entities"][entity]["sitelinks"][f"{self.lang_code}wiki"]["url"]:
                                #print(data["entities"][entity])
                                entities[article] = entity
                        else:
                            print(data["entities"][entity])

                def populate(wd_id: str) -> None:
                    self.article = data["entities"][wd_id]["sitelinks"][f"{self.lang_code}wiki"]["url"]
                    self.desc = data["entities"][wd_id]["descriptions"][f"{self.lang_code}"]["value"]
                    self.num_of_langs = 0
                    self.num_of_sitelinks = 0
                    for sitelink in data["entities"][wd_id]["sitelinks"]:
                        self.num_of_sitelinks += 1
                        if re.search(r"wiki$",sitelink):
                            self.num_of_langs += 1
                    self.wikidata_id = data["entities"][wd_id]["id"]

                for article in self.possible_articles:
                    wd_id = entities[article]
                    if wd_id is not None and "descriptions" in data["entities"][wd_id]:
                        for keyword in self.keywords:
                            try:
                                if keyword.casefold() in data["entities"][wd_id]["descriptions"][f"{self.lang_code}"]["value"].casefold():
                                    populate(wd_id)
                                    break
                            except KeyError:
                                print("KEYERROR: " + str(data["entities"][wd_id]["descriptions"]))
                                pass
                        else: # nobreak:
                            continue
                        break
                else: # nobreak
                    populate(entities[self.possible_articles[0]])
            else:
                self.warning = True
                raise Exception("No \"entities\" in json data", data)

            return self

        def fill_pageviews(self, timeout: float = 5) -> 'Wikifame':
            """
            If self.article is populated, this populates self.pageviews
            """

            # rem = re.search(r"(\|[^\|\n]*)$|([^\|\n]+)$",self.article)
            # if rem is None:
            #     article = self.article[rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
            #     return self
            # article = self.article[rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
            article_url_bit = get_url_bit(self.article)
            try:
                pageviews = get_pageviews(article_url_bit, project=f"{self.lang_code}.wikipedia.org", timeout=timeout)
            except requests.HTTPError:
                printv(0, "ERROR: HTTP Error")
                self.warning = True
                raise
            self.pageviews = pageviews
            print(f"self.pageviews is {self.pageviews}")
            return self

        def search_up_article(self, timeout: float = 5) -> 'Wikifame':
            """
            If self.search_phrase is populated, this populates self.article
            """

            if self.search_phrase is None:
                self.set("article","ERROR: No Search Phrase")
                raise Exception
            try:
                article = search_article_url(self.search_phrase, timeout)
                if article is None:
                    self.set("article","ERROR: No Articles Found")
                    self.warning = True
                    raise Wikifame.NoArticlesFound
                self.set("article",article)
            except requests.HTTPError:
                self.set("article","ERROR: HTTP Error")
                raise
            except Wikifame.NoArticlesFound:
                self.warning = True
                raise
            return self

        def fill_description(self, timeout: float = 5) -> 'Wikifame':
            """
            If "article" is populated, this populates "description"
            """

            # if self.article is None:
            #     self.search_up_article(timeout=timeout)

            rem = re.search(r"(\|[^\|\n]*)$|([^\|\n]+)$",self.article)
            if rem is None:
                return self
            article = self.article[rem.span()[0]:rem.span()[1]].replace("|","").replace(" ","")
            try:
                desc = get_desc([article], timeout=timeout)[0]
            except requests.HTTPError:
                self.set("desc","ERROR: HTTP Error")
                self.warning = True
                raise
            self.set("desc",desc)
            return self

def get_url_bit(url: str) -> str:
    rem = re.search(r"\.wikipedia\.org\/wiki\/(.+)",url)
    if rem:
        return rem.group(1)
    return os.path.basename(parse.urlparse(url).path)

### Possible Searches
# https://en.wikipedia.org/w/api.php?action=opensearch&redirects=resolve&format=json&limit=10&search=11
# https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srqiprofile=wsum_inclinks_pv&srsearch=11
# https://www.wikidata.org/w/api.php?action=query&list=search&format=json&srqiprofile=wsum_inclinks_pv&srsearch=11
def search_possible_articles(
    search_phrase: str,
    limit: int = 10,
    lang_code: str = DEFAULT_LANG,
    timeout: float = 5
    ) -> List[str]:
    """
    Given a search phrase, returns the top {limit} article URLs after searching {lang_code}.wikipedia.org

    :param search_phrase: The search phrase that you want to search {lang_code}.wikipedia.org with.
    :param limit: The maximum number of search results to return.
    :param lang_code: The language code to use.  This should result in {lang_code}.wikipedia.org being valid.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The article URLs of the top {limit} search results
    """

    possible_articles = []

    # https://en.wikipedia.org/w/api.php?action=opensearch&redirects=resolve&format=json&limit=10&search=11
    URL = f"https://{lang_code}.wikipedia.org/w/api.php"
    PARAMS = {
        "action": "opensearch",
        "redirects": "resolve",
        "format": "json",
        "limit": limit,
        "search": search_phrase,
    }

    try:
        resp = requests.get(url=URL, params=PARAMS, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError:
        raise
    data = resp.json()

    try:
        for article in data[3]:
            possible_articles.append(article)
    except:
        raise
    return possible_articles

def wikidata_wbgetentities(
    titles: List[str],
    sites: List[str],
    timeout: float = 5,
    props: str = "info|sitelinks|descriptions|sitelinks/urls"
    ) -> Dict:
    """
    Gets wikibase entity information for titles and sites.  Note that multiple titles should be used with a
    single site and multiple sites should be used with a single title

    :param titles: The titles to search for (titles= parameter)
    :param sites: The sites to search in (sites= parameter)
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The JSON response from the server
    """

    # https://www.wikidata.org/w/api.php?action=wbgetentities&sites=enwiki&format=json&props=info|sitelinks|descriptions|sitelinks/urls&titles=11
    URL = "https://www.wikidata.org/w/api.php"
    PARAMS = {
        "action": "wbgetentities",
        "sites": "|".join(sites),
        "format": "json",
        "props": props,
        "titles": "|".join(titles)
    }

    PARAMS_STR = "&".join("%s=%s" % (k,v) for k,v in PARAMS.items())

    try:
        resp = requests.get(url=URL, params=PARAMS_STR, headers=headers, timeout=timeout)
        print(resp.url)
        resp.raise_for_status()
    except requests.HTTPError:
        raise

    return resp.json()

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
        article = get_url_bit(contents[3][0])
    except:
        article = None
    printv(1, "   > Searched: {} -> {}".format(search_phrase, article))
    return article

def get_pageviews(
    article_url_bit: str, 
    project: str = "{}.wikipedia.org".format(DEFAULT_LANG),
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
    
    article_url_bit = article_url_bit.replace("|","").replace(" ","") # This should be eventually removed
    pageviews = 0
    if article_url_bit != "":
        wiki_url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        wiki_url += "{}/{}/{}/{}/{}/{}/{}".format(project, access, agent, article_url_bit, granularity, start, end)
        try:
            resp = requests.get(wiki_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            raise
        contents: str = resp.json()
        printv(3, json.dumps(contents, indent=4))
        for item in contents["items"]:
            pageviews += item["views"]
        printv(1, "   > Queried: {:14d} | {}".format(pageviews, article_url_bit))
    return pageviews

def get_desc(articles: List[str] = [], project: str = f"{DEFAULT_LANG}.wikipedia.org", timeout: float = 5) -> List[str]:
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
        redir: List[str] = [parse.unquote(arti) for arti in articles[i:i+l]]

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
    # Generic tests
    if True:
        get_pageviews("Noodle")
        get_pageviews("")
        get_pageviews("Donald_Trump")
        search_article_url("Rakhmat Akilov")
        get_pageviews(search_article_url("Rakhmat Akilov"))
        search_article_url("Noodles")
        get_pageviews(search_article_url("Stoke on Trent"))
        get_desc(["Apple"])[0]
        get_desc(["A","9_(number)","ILEUFLIDWUF","D","are_You_the_One%3F","Joe_Biden","WLIEHFW","6_{number)"])

    else:
        search_article_url("Noodles")
    