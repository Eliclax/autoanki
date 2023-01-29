# autoanki
A tool for ordering anki cards based on how "famous" or "notable" it is. WIP.

## Current features:
- Batch-search wikipedia.org for articles using a dynamic search phrase, language, and keywords. (Not fully tested.)
- Gets the number of non-bot article pageviews received between 2015-07-01 and 2023-01-01.
- Gets the number of languages that have a Wikipedia page for the corresponding topic.
- Gets the article URL and a short description of the article.
- Records these on each note.
- It also creates fields containing the article URL, and a short description of the article.

## Planned features:
- Get number of hits from Google search?  (This is very difficult because Google API limits queries to some small number per day... in fact this might be faster manually!)
- A system for fixing wrong search results by manually editing the URL field.
- Order the deck based on some field (including the pageviews/hits/fame field)

See the issues tab for features or enhancements that I'm currently working on.

## Report Bugs

Report bugs on the issues tab at https://github.com/Eliclax/autoanki/issues