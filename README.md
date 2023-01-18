# autoanki
A tool for ordering anki cards based on how "famous" or "notable" it is. WIP.

Currently, it can batch-search en.wikipedia.org for articles using a customisable dynamic search phrase and create a field in the current notes, writing into it the number of non-bot pageviews the articles received between 2015-07-01 and 2023-01-01. It also creates fields containing the article URL, and a short description of the article.

## Planned features:
- Get number of hits from Google search?  (This is very difficult because Google API limits queries to some small number per day... in fact this might be faster manually!)
- A system for fixing wrong search results by manually editing the URL field.
- Order the deck based on some field (including the pageviews/hits/fame field)

See the issues tab for features or enhancements that I'm currently working on.