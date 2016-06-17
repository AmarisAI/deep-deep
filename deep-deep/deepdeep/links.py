# -*- coding: utf-8 -*-
import re
from urllib.parse import urljoin
from typing import Iterator, Dict, Optional, Set, Iterable, Union, Tuple

from formasaurus.utils import get_domain
from scrapy.http import TextResponse
from scrapy.linkextractors import IGNORED_EXTENSIONS
from scrapy.utils.response import get_base_url
from scrapy.utils.url import url_has_any_extension

from deepdeep.utils import canonicalize_url

_NEW_IGNORED = {'7z', '7zip', 'xz', 'gz', 'tar', 'bz2', 'cdr', 'apk'}
_IGNORED = set(IGNORED_EXTENSIONS) | _NEW_IGNORED
_IGNORED = {'.' + e for e in _IGNORED}


js_link_search = re.compile(r"(javascript:)?location\.href=['\"](?P<url>.+)['\"]").search
def extract_js_link(href):
    """
    >>> extract_js_link("javascript:location.href='http://www.facebook.com/rivervalleyvet';")
    'http://www.facebook.com/rivervalleyvet'
    >>> extract_js_link("location.href='http://www.facebook.com/rivervalleyvet';")
    'http://www.facebook.com/rivervalleyvet'
    >>> extract_js_link("javascript:href='http://www.facebook.com/rivervalleyvet';") is None
    True
    """
    m = js_link_search(href)
    if m:
        return m.group('url')


def extract_link_dicts(selector, base_url):
    """
    Extract dicts with link information::

    {
        'url': '<absolute URL>',
        'attrs': {
            '<attribute name>': '<value>',
            ...
        },
        'inside_text': '<text inside link>',
        # 'before_text': '<text preceeding this link>',
    }
    """
    selector.remove_namespaces()

    for a in selector.xpath('//a'):
        link = {}

        attrs = a.root.attrib
        if 'href' not in attrs:
            continue

        href = attrs['href']
        if 'mailto:' in href:
            continue

        js_link = extract_js_link(href)
        if js_link:
            href = js_link
            link['js'] = True

        url = urljoin(base_url, href)
        if url_has_any_extension(url, _IGNORED):
            continue

        link['url'] = url
        link['attrs'] = dict(attrs)

        link_text = a.xpath('normalize-space()').extract_first(default='')
        img_link_text = a.xpath('./img/@alt').extract_first(default='')
        link['inside_text'] = ' '.join([link_text, img_link_text]).strip()

        # TODO: fix before_text and add after_text
        # link['before_text'] = a.xpath('./preceding::text()[1]').extract_first(default='').strip()[-100:]

        yield link


def iter_response_link_dicts(response: TextResponse,
                             limit_by_domain: bool=True) -> Iterator[Dict]:
    base_url = get_base_url(response)
    domain_from = get_domain(response.url)
    for link in extract_link_dicts(response.selector, base_url):
        link['domain_to'] = get_domain(link['url'])
        if limit_by_domain and link['domain_to'] != domain_from:
            continue
        link['domain_from'] = domain_from
        yield link


class DictLinkExtractor:
    """
    A custom link extractor. It returns link dicts instead of Link objects.
    DictLinkExtractor is not compatible with Scrapy link extractors.
    """
    def __init__(self):
        self.seen_urls = set()

    def iter_link_dicts(self,
                        response: TextResponse,
                        limit_by_domain: bool=True,
                        deduplicate: bool=True,
                        deduplicate_local: bool=True
                        ) -> Iterator[Dict]:
        """
        Extract links from the response.
        If ``limit_by_domain`` is True (default), only links for to the same
        domain as response.url will be returned.
        If ``deduplicate`` is True (default), links with seen URLs
        are not returned.
        If ``deduplicate_local`` is True (default), links which are duplicate
        on a page are not returned.
        """
        links = iter_response_link_dicts(response, limit_by_domain)
        if deduplicate:
            links = self.deduplicate_links(links)
        elif deduplicate_local:
            links = self.deduplicate_links(links, seen_urls=set())
        return links

    def deduplicate_links_enumerated(self,
                                     links: Iterable[Dict],
                                     seen_urls: Optional[Set]=None
                                     ) -> Iterator[Tuple[int, Dict]]:
        """
        Filter out links with duplicate URLs. See :meth:`deduplicate_links`.
        """
        if seen_urls is None:
            seen_urls = self.seen_urls
        for idx, link in enumerate(links):
            url = link['url']
            canonical = canonicalize_url(url)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            yield idx, link

    def deduplicate_links(self,
                          links: Iterable[Dict],
                          seen_urls: Optional[Set]=None
                          ) -> Iterator[Dict]:
        """
        Filter out links with duplicate URLs.
        Requests are also filtered out in Scheduler by dupefilter.
        Here we filter them to avoid creating unnecessary requests
        in first place; it helps other components like CrawlGraphMiddleware.
        """
        return (link for idx, link in
                self.deduplicate_links_enumerated(links, seen_urls))
