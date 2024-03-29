from urllib import request, parse
import json
import os
from typing import Union

from aiohttp.client import ClientSession
import asyncio

# If running this module by itself for dev purposes, you can change the verbosity by changing the "v = 1" line
verbose: int = 0
v = 1

if __name__ == "__main__":
    verbose = v

async def searchArticleUrl(searchPhrase : str, session: ClientSession) -> Union[str, None]:
    """
    Given a search phrase, returns the top result after Searching en.wikipedia.org

    :param searchPhrase: The sdearch phrase that you want to search en.wikipedia.org with
    :param session: The ClientSession.  See aiohttp.ClientSession
    :return: The title of the article, as a URL string.
    """

    searchUrl = "https://en.wikipedia.org/w/api.php?action=opensearch&search="
    searchUrl += parse.quote(searchPhrase)
    searchUrl += "&limit=10&namespace=0&format=json"
    print("Searching {}".format(searchPhrase))
    resp = await session.get(searchUrl)
    await asyncio.sleep(1)
    print("Done searching {}".format(searchPhrase))
    resp.raise_for_status()
    search_result = json.loads(await resp.text())
    article = os.path.basename(parse.urlparse(search_result[3][0]).path)
    if verbose >= 1:
        print("   > Searched: {} -> {}".format(searchPhrase, article))
    return article

async def getPageviews(
    article: Union[str, None], 
    session: ClientSession,
    project: str = "en.wikipedia.org",
    access: str = "all-access",
    agent: str = "user",
    granularity: str = "monthly",
    start: str = "20150701",
    end: str = "20230101",
    ) -> int:
    """
    Gets the Wikipedia pageviews over a timeframe, given a URL-encoded Wikipedia article title. If empty, returns 0. See https://wikimedia.org/api/rest_v1/#

    :param article: The title of any article in the specified project. Any spaces should be replaced with underscores. It also should be URI-encoded, so that non-URI-safe characters like %, / or ? are accepted. Example: Are_You_the_One%3F.
    :param session: The ClientSession.  See aiohttp.ClientSession
    :param project: If you want to filter by project, use the domain of any Wikimedia project, for example 'en.wikipedia.org', 'www.mediawiki.org' or 'commons.wikimedia.org'.
    :param access: If you want to filter by access method, use one of desktop, mobile-app or mobile-web. If you are interested in pageviews regardless of access method, use all-access. Available values : all-access, desktop, mobile-app, mobile-web
    :param agent: If you want to filter by agent type, use one of user, automated or spider. If you are interested in pageviews regardless of agent type, use all-agents. Available values : all-agents, user, spider, automated
    :param granularity: The time unit for the response data. As of today, the only supported granularity for this endpoint is daily and monthly. Available values : daily, monthly
    :param start: The date of the first day to include, in YYYYMMDD or YYYYMMDDHH format
    :param end: The date of the last day to include, in YYYYMMDD or YYYYMMDDHH format
    :return: The number of pageviews
    """

    if article is None:
        return 0

    pageviews = 0
    wikiUrl = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    wikiUrl += "{}/{}/{}/{}/{}/{}/{}".format(project, access, agent, article, granularity, start, end)
    resp = await session.get(wikiUrl)
    resp.raise_for_status()
    contents = json.loads(await resp.text())
    if verbose >= 2:
        print(json.dumps(json.loads(contents), indent=4))
    for item in contents["items"]:
        pageviews += item["views"]
    if verbose >= 1:
        print("   > Queried: {:14d} | {}".format(pageviews, article))
    return pageviews

    
if __name__ == "__main__":
    async def setup():
        async with ClientSession() as session:
            await asyncio.gather()
            await getPageviews("Staffordshire", session)
            await getPageviews("Noodle", session)
            await getPageviews("", session)
            await getPageviews("Donald_Trump", session)
            await searchArticleUrl("Noodles", session)
            await getPageviews(await searchArticleUrl("Stoke on Trent", session), session)

    asyncio.run(setup())