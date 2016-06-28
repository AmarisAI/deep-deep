# -*- coding: utf-8 -*-
import time
import itertools
import functools
import collections
from urllib.parse import unquote_plus
from urllib.parse import urlsplit

import numpy as np
import parsel
import lxml.html
from lxml import etree
from lxml.html.clean import Cleaner
from formasaurus.utils import get_domain
from scrapy.utils.url import canonicalize_url as _canonicalize_url


def dict_aggregate_max(*dicts):
    """
    Aggregate dicts by keeping a maximum value for each key.

    >>> dct1 = {'x': 1, 'z': 2}
    >>> dct2 = {'x': 3, 'y': 5, 'z': 1}
    >>> dict_aggregate_max(dct1, dct2) == {'x': 3, 'y': 5, 'z': 2}
    True
    """
    res = {}
    for dct in dicts:
        for key, value in dct.items():
            res[key] = max(res.get(key, value), value)
    return res


def get_response_domain(response):
    return response.meta.get('domain', get_domain(response.url))


def set_request_domain(request, domain):
    request.meta['domain'] = domain


def decreasing_priority_iter(N=5):
    # First N random links get priority=0,
    # next N - priority=-1, next N - priority=-2, etc.
    # This way scheduler will prefer to download
    # pages from many domains.
    for idx in itertools.count():
        priority = - (idx // N)
        yield priority


def url_path_query(url):
    """
    Return URL path and query, without domain, scheme and fragment:

    >>> url_path_query("http://example.com/foo/bar?k=v&egg=spam#id9")
    '/foo/bar?k=v&egg=spam'
    """
    p = urlsplit(url)
    return unquote_plus(p.path + '?' + p.query).lower()


def softmax(z, t=1.0):
    """
    Softmax function with temperature.

    >>> softmax(np.zeros(4))
    array([ 0.25,  0.25,  0.25,  0.25])
    >>> softmax([])
    array([], dtype=float64)
    >>> softmax([-2.85, 0.86, 0.28])  # DOCTEST: +ELLIPSES
    array([ 0.015...,  0.631...,  0.353...])
    >>> softmax([-2.85, 0.86, 0.28], t=0.00001)
    array([ 0.,  1.,  0.])
    """
    if not len(z):
        return np.array([])

    z = np.asanyarray(z) / t
    z_exp = np.exp(z - np.max(z))
    return z_exp / z_exp.sum()


class MaxScores:
    """
    >>> s = MaxScores()
    >>> s.update("foo", 0.2)
    >>> s.update("foo", 0.1)
    >>> s.update("bar", 0.5)
    >>> s.update("bar", 0.6)
    >>> s['unknown']
    0
    >>> s['foo']
    0.2
    >>> s['bar']
    0.6
    >>> s.sum()
    0.8
    >>> s.avg()
    0.4
    >>> len(s)
    2
    """
    def __init__(self, default=0):
        self.default = default
        self.scores = collections.defaultdict(lambda: default)

    def update(self, key, value):
        self.scores[key] = max(self.scores[key], value)

    def sum(self):
        return sum(self.scores.values())

    def avg(self):
        if len(self) == 0:
            return 0
        return self.sum() / len(self)

    def __getitem__(self, key):
        if key not in self.scores:
            return self.default
        return self.scores[key]

    def __len__(self):
        return len(self.scores)


def log_time(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            end = time.time()
            print("{} took {:0.4f}s".format(func, end-start))
    return wrapper


_clean_html = Cleaner(
    scripts=True,
    javascript=False,  # onclick attributes are fine
    comments=True,
    style=True,
    links=True,
    meta=True,
    page_structure=False,  # <title> may be nice to have
    processing_instructions=True,
    embedded=True,
    frames=True,
    forms=False,  # keep forms
    annoying_tags=False,
    remove_unknown_tags=False,
    safe_attrs_only=False,
).clean_html


def _cleaned_html_tree(html: str) -> lxml.html.HtmlElement:
    parser = lxml.html.HTMLParser(encoding='utf8')
    tree = lxml.html.fromstring(html.encode('utf8'), parser=parser)
    return _clean_html(tree)


def _selector_to_text(sel: parsel.Selector) -> str:
    return sel.xpath('normalize-space()').extract_first('')


def html2text(html: str) -> str:
    """
    Convert html to text.

    >>> html = '<html><style>.div {}</style><body><p>Hello,   world!</body></html>'
    >>> html2text(html)
    'Hello, world!'

    It works with XHTML declared ecodings:
    >>> html = '<?xml version="1.0" encoding="utf-8" ?><html><style>.div {}</style><body>Hello,   world!</p></body></html>'
    >>> html2text(html)
    'Hello, world!'

    >>> html2text("")
    ''
    """
    try:
        tree = _cleaned_html_tree(html)
        sel = parsel.Selector(root=tree, type='html')
    except (etree.XMLSyntaxError, etree.ParseError):
        # likely plain text
        sel = parsel.Selector(html)
    return _selector_to_text(sel)


@functools.lru_cache(maxsize=100000)
def canonicalize_url(url):
    return _canonicalize_url(url)
