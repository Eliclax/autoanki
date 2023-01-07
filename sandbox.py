from urllib import request, parse
import json
import os



def getWikiPageviews(
    searchPhrase: str = "", 
    article: str = "", 
    project: str = "en.wikipedia.org",
    access: str = "all-access",
    agent: str = "user",
    granularity: str = "monthly",
    start: str = "20150701",
    end: str = "20230101"
    ) -> int:
    """
    Gets the Wikipedia pageviews over a timeframe, given a Wikipedia Search phrase or article. If using a search phrase, but there are no search results, returns 0. See https://wikimedia.org/api/rest_v1/#

    :param searchPhrase: What to search Wikipedia for.  The first page returned will be used.  If none are returned this function will return 0.
    :param article: The title of any article in the specified project. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param project: If you want to filter by project, use the domain of any Wikimedia project, for example 'en.wikipedia.org', 'www.mediawiki.org' or 'commons.wikimedia.org'.
    :param access: If you want to filter by access method, use one of desktop, mobile-app or mobile-web. If you are interested in pageviews regardless of access method, use all-access. Available values : all-access, desktop, mobile-app, mobile-web
    :param agent: If you want to filter by agent type, use one of user, automated or spider. If you are interested in pageviews regardless of agent type, use all-agents. Available values : all-agents, user, spider, automated
    :param granularity: The time unit for the response data. As of today, the only supported granularity for this endpoint is daily and monthly. Available values : daily, monthly
    :param start: The date of the first day to include, in YYYYMMDD or YYYYMMDDHH format
    :param end: The date of the last day to include, in YYYYMMDD or YYYYMMDDHH format
    :return: The number of pageviews
    """

    assert article != "" or searchPhrase != ""

    print("Article: " + article)

    if article == "":
        #SEE https://stackoverflow.com/questions/27457977/searching-wikipedia-using-api
        searchUrl = "https://en.wikipedia.org/w/api.php?action=opensearch&search="
        searchUrl += parse.quote(searchPhrase)
        searchUrl += "&limit=10&namespace=0&format=json"
        search_result = json.loads(request.urlopen(searchUrl).read())
        #print(search_result)
        article = os.path.basename(parse.urlparse(search_result[3][0]).path)
        # notes[i]["url_bit"] = url_bit
        # notes[i]["wikiUrls"] = copy.deepcopy(search_result[3])
        print("Article: " + article)

    pageviews = 0
    wikiUrl = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    wikiUrl += "{}/{}/{}/{}/{}/{}/{}".format(project, access, agent, article, granularity, start, end)
    contents = json.loads(request.urlopen(wikiUrl).read())
    for item in contents["items"]:
        #print(item)
        pageviews += item["views"]
    return pageviews



print(getWikiPageviews("Joe Biden", ""))