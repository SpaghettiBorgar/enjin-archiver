import requests
from bs4 import BeautifulSoup
import os
from os.path import *
import re
from urllib.parse import urlparse
import config
import dbm.gnu
import json
import hashlib

api_db = dbm.gnu.open('api_cache.db', 'cf')
asset_db = dbm.gnu.open('assets.db', 'cf')

cookies = {}
for cookie in config.cookie.split('; '):
	key, value = cookie.split('=')
	cookies[key] = value

session = requests.Session()
session.cookies.update(cookies)
session.headers[
    'User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36"


class ForeignURLException(Exception):
	pass


def get_ext(url):
	parsed = urlparse(url)
	root, ext = splitext(parsed.path)
	return ext


def sizeof_fmt(num, suffix="B"):
	for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
		if abs(num) < 1024.0:
			return f"{num:3.1f}{unit}{suffix}"
		num /= 1024.0
	return f"{num:.1f}Yi{suffix}"


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
	soup = BeautifulSoup(fetch(url), "lxml")
	for img in soup.find_all("img"):
		save_asset(img['src'])
	return soup


_api_req_id = 100000


def api_req(method, params):
	global _api_req_id
	key = json.dumps({'method': method, 'params': params})
	if key in api_db:
		return json.loads(api_db.get(key))
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
	api_db[key] = json.dumps(res['result'])
	return res['result']


def save_asset(url):
	if len(url) == 0:
		return
	url = urlparse(url)
	if not url.netloc:
		url = url._replace(netloc=config.enjin_site)._replace(scheme="https")
	if url.netloc == "www.danasoft.com":
		return
	url = url.geturl()
	if url in asset_db:
		return

	try:
		print(f"[HTTP] GET {url} ... ", end='', flush=True)
		response = session.get(url)
		print(response.status_code)
		response.raise_for_status()
	except requests.HTTPError as e:
		if response.status_code == 403 or response.status_code == 404 or response.status_code == 410:
			asset_db[url] = ""
		else:
			return
	except requests.ConnectionError:
		return

	md5_hash = hashlib.md5(response.content).hexdigest()
	asset_db[url] = md5_hash
	os.makedirs("assets", exist_ok=True)
	path = "assets/" + md5_hash + get_ext(url)
	if isfile(path):
		return
	with open(path, 'wb') as f:
		written = f.write(response.content)
		print(f'written {sizeof_fmt(written)} to {path}')
