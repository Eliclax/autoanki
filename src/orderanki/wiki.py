import json
import os
import requests
from typing import Union
from urllib import parse

# If running this module by itself for dev purposes, you can change the verbosity by changing the "v: int = 1" line
verbose: int = 0
v: int = 1

headers = {'User-Agent': 'AutoankiBot/0.1 (https://github.com/Eliclax/autoanki; tw2000x@gmail.com)'}

if __name__ == "__main__":
    verbose = v

def searchArticleUrl(searchPhrase: str, timeout: float = 5) -> Union[str, None]:
    """
    Given a search phrase, returns the top result after Searching en.wikipedia.org

    :param searchPhrase: The sdearch phrase that you want to search en.wikipedia.org with.
    :param timeout: How many seconds to wait for the server to send data before giving up.
    :return: The title of the article, as a URL string.
    """

    searchUrl = "https://en.wikipedia.org/w/api.php?action=opensearch&search="
    searchUrl += parse.quote(searchPhrase)
    searchUrl += "&limit=10&namespace=0&format=json"
    try:
        resp = requests.get(searchUrl, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError:
        raise
    search_result = resp.json()
    try:
        article = os.path.basename(parse.urlparse(search_result[3][0]).path)
    except:
        return None
    if verbose >= 1:
        print("   > Searched: {} -> {}".format(searchPhrase, article))
    return article

def getPageviews(
    article: Union[str, None], 
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
        wikiUrl = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        wikiUrl += "{}/{}/{}/{}/{}/{}/{}".format(project, access, agent, article, granularity, start, end)
        try:
            resp = requests.get(wikiUrl, headers=headers, timeout=timeout)
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

if __name__ == "__main__":
    getPageviews("Noodle")
    getPageviews("")
    getPageviews("Donald_Trump")
    searchArticleUrl("Noodles")
    getPageviews(searchArticleUrl("Stoke on Trent"))