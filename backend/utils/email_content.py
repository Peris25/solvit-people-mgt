"""Validate actual message content before branding can hide an empty email."""
import re
from html import unescape
from html.parser import HTMLParser


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'head', 'template'}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'head', 'template'} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def message_body(html):
    if not isinstance(html, str):
        return ''
    if '<!--solvit-wrapped-->' not in html:
        return html
    # New retries carry explicit body boundaries; support previously queued wrappers too.
    match = re.search(r'<!--solvit-body-start-->(.*?)<!--solvit-body-end-->', html, re.S)
    if not match:
        match = re.search(r'<tr><td style="padding:18px 32px 28px 32px;[^"]*">(.*?)</td>\s*</tr>', html, re.S)
    return match.group(1) if match else ''


def meaningful(value, html=False):
    if not isinstance(value, str):
        return False
    if html:
        parser = _VisibleText()
        parser.feed(message_body(value))
        value = ' '.join(parser.parts)
    value = re.sub(r'\{\{.*?\}\}', '', unescape(value), flags=re.S)
    value = re.sub(r'[\s\u200b-\u200f\ufeff]+', ' ', value).strip()
    return bool(value) and value.casefold() not in {'(no body)', 'no body', '(no content)', 'no content', 'undefined', 'null', 'none'}


def content_error(subject, html):
    if not meaningful(subject) or any(char in subject for char in '\r\n'):
        return 'Email subject is empty or invalid'
    if not meaningful(html, html=True):
        return 'Email message body is empty or invalid'
    return None
