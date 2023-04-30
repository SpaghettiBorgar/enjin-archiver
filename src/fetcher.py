import requests
from bs4 import BeautifulSoup
import os
from os.path import *
import re
from urllib.parse import urlparse
import config
import dbm.gnu
import json

db = dbm.gnu.open('api_cache.db', 'cf')

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


_api_req_id = 100000


def api_req(method, params):
	global _api_req_id
	key = json.dumps({'method': method, 'params': params})
	if key in db:
		return json.loads(db.get(key))
	print(f"[HTTP] POST api {method} {params} ... ", end='', flush=True)
	response = session.post(f"https://{config.enjin_site}/api/v1/api.php",
	                        json={
	                            'jsonrpc': '2.0',
	                            'id': _api_req_id,
	                            'method': method,
	                            'params': params
	                        })
	print(response.status_code)
	_api_req_id += 1
	response.raise_for_status()
	res = response.json()
	if 'error' in res:
		print(res)
		return None
	db[key] = json.dumps(res['result'])
	return res['result']
