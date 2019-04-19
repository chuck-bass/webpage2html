#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import base64
import datetime
import os
import re
import sys
import timeit

import requests
from bs4 import BeautifulSoup
from termcolor import colored
from aiohttp import request
import asyncio


if sys.version > '3':
    from urllib.parse import urlparse, urlunsplit, urljoin, quote
else:
    from urlparse import urlparse, urlunsplit, urljoin
    from urllib import quote


def log(s, color=None, on_color=None, attrs=None, new_line=True):
    if not color:
        print(str(s), end=' ', file=sys.stderr)
    else:
        print(colored(str(s),
                      color, on_color, attrs), end=' ', file=sys.stderr)
    if new_line:
        sys.stderr.write('\n')
    sys.stderr.flush()


def absurl(index, relpath=None, normpath=None):
    if normpath is None:
        normpath = lambda x: x

    index_validate = (index.lower().startswith('http')
                      or index.lower().startswith('https'))
    relpath_validate = (relpath and
                        (relpath.startswith('http')
                         or relpath.startswith('https')))
    if index_validate or relpath_validate:
        new = urlparse(urljoin(index, relpath))
        return urlunsplit((new.scheme, new.netloc, normpath(new.path), new.query, ''))
        # netloc contains basic auth, so do not use domain
    else:
        if relpath:
            return normpath(os.path.join(os.path.dirname(index), relpath))
        else:
            return index


async def fetch(url, method='GET', headers=None,
                verbose=True, ignore_error=False):
    async with request(method, url, headers=headers) as response:
        if verbose:
            # log('fetch url : {}'.format(url))
            log('[ {} ] {} - {}'.format(method,
                                        response.status, response.url))

        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0'
            }

        if not ignore_error and (response.status >= 400
                                 or response.status < 200):
            content = ''
        elif response.content_type.lower().startswith('text/'):
            content = await response.text()
        elif response.content_type.lower() == 'application/json':
            content = await response.json()
        else:
            # 默认 为 bytes 的情况
            content = await response.read()
        return content, {'url': str(response.url),
                         'content-type': response.content_type}


async def getAsync(index, relpath=None, verbose=True, verify=True,
                   ignore_error=False):
    index_validate = (index.startswith('http')
                      or index.startswith('https'))
    relpath_validate = (relpath and
                        (relpath.startswith('http')
                         or relpath.startswith('https')))
    if index_validate or relpath_validate:
        full_path = absurl(index, relpath)
        if not full_path:
            if verbose:
                log('[ WARN ] invalid path, %s %s' % (index, relpath),
                    'yellow')
            return '', None

        full_path = quote(full_path, safe="%/:=&?~#+!$,;'@()*[]")

        try:
            return await fetch(full_path)
        except Exception as ex:
            if verbose:
                log('[ WARN ] %s - %s %s' % ('???', full_path, ex), 'yellow')
            return '', None

    else:
        if verbose:
            log('[ ERROR ] invalid index - %s' % index, 'red')
        return '', None


async def data_to_base64(index, src, verbose=True):
    # doc here: http://en.wikipedia.org/wiki/Data_URI_scheme
    sp = urlparse(src).path.lower()
    if src.strip().startswith('data:'):
        return src
    if sp.endswith('.png'):
        fmt = 'image/png'
    elif sp.endswith('.gif'):
        fmt = 'image/gif'
    elif sp.endswith('.ico'):
        fmt = 'image/x-icon'
    elif sp.endswith('.jpg') or sp.endswith('.jpeg'):
        fmt = 'image/jpg'
    elif sp.endswith('.svg'):
        fmt = 'image/svg+xml'
    elif sp.endswith('.ttf'):
        fmt = 'application/x-font-ttf'
    elif sp.endswith('.otf'):
        fmt = 'application/x-font-opentype'
    elif sp.endswith('.woff'):
        fmt = 'application/font-woff'
    elif sp.endswith('.woff2'):
        fmt = 'application/font-woff2'
    elif sp.endswith('.eot'):
        fmt = 'application/vnd.ms-fontobject'
    elif sp.endswith('.sfnt'):
        fmt = 'application/font-sfnt'
    elif sp.endswith('.css') or sp.endswith('.less'):
        fmt = 'text/css'
    elif sp.endswith('.js'):
        fmt = 'application/javascript'
    else:
        # what if it's not a valid font type? may not matter
        fmt = 'image/png'
    # data, extra_data = get(index, src, verbose=verbose)
    data, extra_data = await getAsync(index, src, verbose=verbose)
    if extra_data and extra_data.get('content-type'):
        fmt = extra_data.get('content-type').replace(' ', '')
    if data:
        if sys.version > '3':
            if type(data) is bytes:
                return ('data:%s;base64,' % fmt) + bytes.decode(base64.b64encode(data))
            else:
                return ('data:%s;base64,' % fmt) + bytes.decode(base64.b64encode(str.encode(data)))
        else:
            reload(sys)
            sys.setdefaultencoding('utf-8')
            return ('data:%s;base64,' % fmt) + base64.b64encode(data)
    else:
        return absurl(index, src)


css_encoding_re = re.compile(r'''@charset\s+["']([-_a-zA-Z0-9]+)["']\;''', re.I)


async def handle_css_content(index, css, verbose=True):
    if not css:
        return css
    if not isinstance(css, str):
        if sys.version > '3':
            css = bytes.decode(css)
            mo = css_encoding_re.search(css)
        else:
            mo = css_encoding_re.search(css)
        if mo:
            try:
                css = css.decode(mo.group(1))
            except Exception:
                log('[ WARN ] failed to convert css to encoding {}'
                    .format(mo.group(1)),
                    'yellow')
    # Watch out! how to handle urls which contain parentheses inside? Oh god,
    # css does not support such kind of urls
    # I tested such url in css, and, unfortunately, the css rule is broken.
    # LOL!
    # I have to say that, CSS is awesome!
    reg = re.compile(r'url\s*\((.+?)\)')
    src_arr = reg.findall(css)
    src_arr = [i.strip(' \'"') for i in src_arr]

    if len(src_arr) == 0:
        return css

    data_arr = await asyncio.gather(*[data_to_base64(index, src, verbose)
                                    for src in src_arr])

    index_func = 0

    def repl(matchobj):
        nonlocal index_func
        data = data_arr[index_func]
        index_func += 1
        return 'url(' + data + ')'

    css = reg.sub(repl, css)
    return css


async def generate(index, verbose=True, keep_script=False,
                   prettify=False, full_url=True, verify=True,
                   errorpage=False, **kwargs):
    """
    given a index url such as http://www.google.com,
    http://custom.domain/index.html
    return generated single html
     该方法已经被改为异步方法；
     在只有一个 url 时看不出来威力；
     只比 普通同步方法快 一点点；
     在并发 url 的环境下,
     肯定是比同步的要快很多！！！
    """
    html_doc, extra_data = await getAsync(index, verbose=verbose,
                                          verify=verify,
                                          ignore_error=errorpage)

    if extra_data and extra_data.get('url'):
        index = extra_data['url']

    # now build the dom tree
    soup = BeautifulSoup(html_doc, 'lxml')

    async def handle_link():
        for link in soup('link'):
            if link.get('href'):
                if 'mask-icon' in (link.get('rel') or []) or 'icon' in (link.get('rel') or []) or 'apple-touch-icon' in (
                        link.get('rel') or []) or 'apple-touch-icon-precomposed' in (link.get('rel') or []):
                    link['data-href'] = link['href']

                    link['href'] = await data_to_base64(index,
                                                        link['href'],
                                                        verbose=verbose)
                elif link.get('type') == 'text/css' or link['href'].lower().endswith('.css') or 'stylesheet' in (
                        link.get('rel') or []):
                    new_type = 'text/css' if not link.get('type') else link['type']
                    css = soup.new_tag('style', type=new_type)
                    css['data-href'] = link['href']
                    for attr in link.attrs:
                        if attr in ['href']:
                            continue
                        css[attr] = link[attr]
                    css_data, _ = await getAsync(index,
                                                 relpath=link['href'], verbose=verbose)
                    new_css_content = await handle_css_content(absurl
                                                               (index,
                                                                link['href']),
                                                               css_data,
                                                               verbose=verbose)
                    # if "stylesheet/less" in '\n'.join(link.get('rel') or []).lower():
                    # fix browser side less: http://lesscss.org/#client-side-usage
                    #     # link['href'] = 'data:text/less;base64,' + base64.b64encode(css_data)
                    #     link['data-href'] = link['href']
                    #     link['href'] = absurl(index, link['href'])
                    if False:  # new_css_content.find('@font-face') > -1 or new_css_content.find('@FONT-FACE') > -1:
                        link['href'] = 'data:text/css;base64,' + base64.b64encode(new_css_content)
                    else:
                        css.string = new_css_content
                        link.replace_with(css)
                elif full_url:
                    link['data-href'] = link['href']
                    link['href'] = absurl(index, link['href'])

    async def handle_js():
        for js in soup('script'):
            if not keep_script:
                js.replace_with('')
                continue
            if not js.get('src'):
                continue
            new_type = 'text/javascript' if not js.has_attr('type') or not js['type'] else js['type']
            code = soup.new_tag('script', type=new_type)
            code['data-src'] = js['src']
            js_str, _ = await getAsync(index, relpath=js['src'], verbose=verbose)
            if type(js_str) == bytes:
                js_str = js_str.decode('utf-8')
            try:
                if js_str.find('</script>') > -1:
                    code['src'] = 'data:text/javascript;base64,' + base64.b64encode(js_str.encode()).decode()
                elif js_str.find(']]>') < 0:
                    code.string = '<!--//--><![CDATA[//><!--\n' + js_str + '\n//--><!]]>'
                else:
                    # replace ]]> does not work at all for chrome, do not believe
                    # http://en.wikipedia.org/wiki/CDATA
                    # code.string = '<![CDATA[\n' + js_str.replace(']]>', ']]]]><![CDATA[>') + '\n]]>'
                    code.string = js_str
            except Exception:
                if verbose:
                    log(repr(js_str))
                raise
            js.replace_with(code)

    async def handle_image():
        src_arr = []
        for img in soup('img'):
            if img.get('src'):
                src_arr.append(img['src'])
            if img.get('data-src'):
                src_arr.append(img['data-src'])

        image_arr = await asyncio.gather(*[data_to_base64(index,
                                                          src) for src in src_arr])
        idx = 0

        for img in soup('img'):
            if img.get('src'):
                img['src'] = image_arr[idx]
                idx += 1
            if img.get('data-src'):
                img['src'] = image_arr[idx]
                idx += 1
                del img['data-src']

            # `img` elements may have `srcset` attributes with multiple sets of images.
            # To get a lighter document it will be cleared, and used only the standard `src` attribute
            # Maybe add a flag to enable the base64 conversion of each `srcset`?
            # For now a simple warning is displayed informing that image has multiple sources
            # that are stripped.

            if img.get('srcset'):
                img['data-srcset'] = img['srcset']
                del img['srcset']
                if verbose:
                    log('[ WARN ] srcset found in img tag. Attribute will be cleared. File src => %s' % (img['data-src']),
                        'yellow')

            def check_alt(attr):
                if img.has_attr(attr) and img[attr].startswith('this.src='):
                    # we do not handle this situation yet, just warn the user
                    if verbose:
                        log('[ WARN ] %s found in img tag and unhandled, which may break page' % (attr), 'yellow')

            check_alt('onerror')
            check_alt('onmouseover')
            check_alt('onmouseout')

    async def handle_tag():
        for tag in soup(True):
            if full_url and tag.name == 'a' and tag.has_attr('href') and not tag['href'].startswith('#'):
                tag['data-href'] = tag['href']
                tag['href'] = absurl(index, tag['href'])
            if tag.has_attr('style'):
                if tag['style']:
                    tag['style'] = await handle_css_content(index,
                                                            tag['style'],
                                                            verbose=verbose)
            elif tag.name == 'link' and tag.has_attr('type') and tag['type'] == 'text/css':
                if tag.string:
                    tag.string = await handle_css_content(index,
                                                          tag.string,
                                                          verbose=verbose)
            elif tag.name == 'style':
                if tag.string:
                    tag.string = await handle_css_content(index,
                                                          tag.string,
                                                          verbose=verbose)

    await asyncio.gather(handle_link(), handle_js(), handle_image(),
                         handle_tag())

    if prettify:
        return soup.prettify(formatter='html')
    else:
        return str(soup)


def usage():
    print("""
usage:

    $ webpage2html [options] some_url

options:

    -h, --help              help page, you are reading this now!
    -q, --quiet             don't show verbose url get log in stderr
    -s, --script            keep javascript in the generated html

examples:

    $ webpage2html -h
        you are reading this help message

    $ webpage2html http://www.google.com > google.html
        save google index page for offline reading, keep style untainted

    $ webpage2html -s http://gabrielecirulli.github.io/2048/ > 2048.html
        save dynamic page with Javascript example
        the 2048 game can be played offline after being saved

    $ webpage2html /path/to/xxx.html > xxx_single.html
        combine local saved xxx.html with a directory named xxx_files together into a single html file
""")


def main():
    kwargs = {}
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--quiet', action='store_true', help="don't show verbose url get log in stderr")
    parser.add_argument('-s', '--script', action='store_true', help="keep javascript in the generated html")
    parser.add_argument('-k', '--insecure', action='store_true', help="ignore the certificate")
    parser.add_argument('-o', '--output', help="save output to")
    parser.add_argument('-u', '--username', help="use HTTP basic auth with specified username")
    parser.add_argument('-p', '--password', help="use HTTP basic auth with specified password")
    parser.add_argument('--errorpage', action='store_true', help="crawl an error page")
    parser.add_argument("url", help="the website to store")
    args = parser.parse_args()

    args.verbose = not args.quiet
    args.keep_script = args.script
    args.verify = not args.insecure
    args.index = args.url
    kwargs = vars(args)

    start = timeit.default_timer()
    loop = asyncio.get_event_loop()
    rs = loop.run_until_complete(generate(**kwargs))
    loop.close()
    end = timeit.default_timer()
    log(str(end-start))
    if args.output and args.output != '-':
        with open(args.output, 'wb') as f:
            f.write(rs.encode())
    else:
        sys.stdout.write(rs)


if __name__ == '__main__':
    main()
