import json
import os
from numpy import isin
import requests
from typing import Union
from urllib import parse, error

headers = {'User-Agent': 'AutoankiBot/0.1 (https://github.com/Eliclax/autoanki; tw2000x@gmail.com)'}

def foo():
    try:
        resp = requests.get('https://en.wikipedia.org/w/api.php?action=opensearch&search=&limit=10&namespace=0&format=json', headers=headers)
        resp.raise_for_status()
        print(resp.status_code)

    except requests.HTTPError as err:
        print("Helllllo")
        raise

def main():
    try:
        foo()
    except requests.HTTPError as err:
        print("Hello, Earth!")
    except Exception as err:
        if isinstance(err, requests.HTTPError):
            print("Hello, World!")

main()