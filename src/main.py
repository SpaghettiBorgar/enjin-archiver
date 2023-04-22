import re
import fetcher
import string
from bs4 import BeautifulSoup
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import IntegrityError
from dateutil.parser import parse as _parsedate, ParserError
import config

# response = requests.get()

Base = declarative_base()


def parsedate(timestr, parserinfo=None, **kwargs):
	try:
		return _parsedate(timestr, parserinfo=None, **kwargs)
	except ParserError:
		return None


class Forum(Base):
	__tablename__ = "forums"
	id_ = Column("id", Integer, primary_key=True)
	name = Column("name", String)
	description = Column("description", String)
	parent = Column("parent", Integer, ForeignKey("forums.id"))


class ForumThread(Base):
	__tablename__ = "threads"
	id_ = Column("id", Integer, primary_key=True)
	title = Column("title", String)
	author = Column("author", String)
	views = Column("views", Integer)
	date = Column("date", Date)
	sticky = Column("sticky", Boolean)
	labels = Column("labels", PickleType)


class VoteType(Base):
	__tablename__ = "vote_types"
	id_ = Column("id", Integer, primary_key=True)
	name = Column("name", String)


class PostVote(Base):
	__tablename__ = "votes"
	id_ = Column("id", Integer, primary_key=True, autoincrement=True)
	user = Column("user", Integer)
	post = Column("post", Integer, ForeignKey("posts.id"))
	type = Column("type", Integer, ForeignKey("vote_types.id"))


class ForumPost(Base):
	__tablename__ = "posts"
	id_ = Column("id", Integer, primary_key=True)
	thread = Column("thread", Integer, ForeignKey("threads.id"))
	author = Column("author", String)
	posted = Column("posted", Date)
	edited = Column("edited", Date)
	content = Column("content", Text)


engine = create_engine(config.dbpath, echo=True)
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()


def parse_forum_page(soup):
	print("parsing forums page")
	i = 0
	for cbox in soup(class_="contentbox"):
		i += 1
		category = next(cbox.select_one(".block-title .text span").stripped_strings)
		session.add(Forum(id_=i, name=category))
		parse_forums_block(cbox, i)


def parse_forums_block(soup, parent_id):
	if soup == None:
		return
	for tr in soup.select(".block-container table tr.row"):
		forum_link = tr.find(class_="forum-name", name="a")
		id_ = re.search(r'/viewforum/(\d+)', forum_link['href']).group(1)
		forum = Forum(id_=id_,
		              name=forum_link.text.strip(),
		              description=tr.find(class_="description").text.strip(),
		              parent=parent_id)
		session.add(forum)
		task_queue.append((process_forum, forum_link['href'], id_))


def process_forum(url, id_):
	soup = fetcher.fetch_soup(url)
	parse_forums_block(soup.find(class_="subforums-block"), id_)
	threads = soup.select_one(".threads")
	tables = threads("table")
	sticky = False
	while len(tables) > 0:
		heading = tables[0].find(class_="heading")
		if heading:
			sticky = "sticky" in heading.find(name="th", class_="thread").text.lower()
		else:
			for tr in tables[0]("tr", class_="row"):
				thread = ForumThread(
				    id_=re.search(r'/viewthread/(\d+)',
				                  tr.find(name="a", class_="thread-view")['href']).group(1),  #
				    title=tr.find(class_="thread-subject").text.strip(),
				    author=re.search(r'/profile/(\w+)',
				                     tr.find(class_="by").a['href']).group(1),
				    date=parsedate(tr.find(name="td", class_="thread")['data-time']),
				    views=int(tr.find(name="td", class_="thread")['data-views']),
				    labels=[(l['title'], re.match(r'background-color:\s*(#?\w+)', l['style']).group(1))
				            for l in tr(class_="forum-label")],
				    sticky=sticky)
				session.add(thread)
				task_queue.append((process_thread, tr.find(name="a", class_="thread-view")['href'], thread.id_))
		tables.pop(0)
	next = next_page_url(soup)
	if next:
		process_forum(next, id_)


def next_page_url(soup):
	page_button = soup.select_one(".element_pagewidget input.right")
	if page_button:
		return re.search(r'\"(.*?)\"', page_button['onclick']).group(1)
	else:
		return None


def process_thread(url, id_):
	soup = fetcher.fetch_soup(url)
	container = soup.select_one(".forum-content .block-container")
	# skip first row on following pages, if it's the recurring thread-starting post
	for tr in container.find_all(name="tr", class_="row")[container.find(class_="new-post-marker") != None:]:
		post = ForumPost(id_=tr['post_id'],
		                 thread=id_,
		                 author=tr.td['data-userid'],
		                 posted=parsedate(tr.find(class_="posted").next.string, fuzzy=True),
		                 edited=parsedate(tr.find(class_="posted").span.text, fuzzy=True),
		                 content=str(tr.find(class_="post-wrapper")))
		session.add(post)
		if vote_type_lookup == {}:
			populate_vote_types(tr)
		for vote in tr.find_all(class_="vote"):  #TODO user votes preview is limited to 21 users
			for user in vote.find_all(class_="user"):
				session.add(
				    PostVote(post=post.id_,
				             user=user.a['data-minitooltip-userid'],
				             type=vote_type_lookup[vote.find(class_="vote_name").string.strip()]))
	next = next_page_url(soup)
	if next:
		process_thread(next, id_)


vote_type_lookup = {}


def populate_vote_types(soup):
	with session.begin_nested():
		for type in soup.find(class_="vote-types").find_all(class_="vote-type"):
			vote_type_lookup[type['data-tooltip']] = type['data-votetypeid']
			session.add(VoteType(id_=type['data-votetypeid'], name=type['data-tooltip']))


task_queue = []

parse_forum_page(fetcher.fetch_soup("/forum"))

while len(task_queue) > 0:
	task = task_queue[0]
	task[0](*task[1:])
	try:
		session.commit()
	except IntegrityError as e:
		session.rollback()
	task_queue.pop(0)

session.commit()
