import requests
from bs4 import BeautifulSoup
import os
from os.path import *
import re
from urllib.parse import urlparse
import config

cookies = {}
for cookie in config.cookie.split('; '):
	key, value = cookie.split('=')
	cookies[key] = value

session = requests.Session()
session.cookies.update(cookies)


class ForeignURLException(Exception):
	pass


def fetch(url):
	host = urlparse(url).netloc
	if not (host == '' or host == config.enjin_site):
		raise ForeignURLException(host)
	url = urlparse(url).path
	furl = normpath(f"pages/" + ("index.html" if url == '/' else url + ".html"))
	try:
		with open(furl) as f:
			return f.read()
	except FileNotFoundError:
		requrl = f"https://{config.enjin_site}/{url}"
		print(f"[HTTP] GET {requrl} ... ", end='', flush=True)
		response = session.get(f"https://{config.enjin_site}/{url}")
		print(response.status_code)
		response.raise_for_status()
		os.makedirs(dirname(furl), exist_ok=True)
		if isfile(furl):
			raise FileExistsError
		with open(furl, 'w') as f:
			f.write(response.text)
		return fetch(url)


def fetch_soup(url):
	return BeautifulSoup(fetch(url), "lxml")
