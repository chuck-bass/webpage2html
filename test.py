# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import re


def test():
    css = 'url(//res.wx.qq.com/mmbizwap/zh_CN/htmledition/images/icon/appmsg/icon_appmsg_msg_closed_sprite.2x42f400.png)url(sss)'

    reg = re.compile(r'url\s*\((.+?)\)')
    res = reg.findall(css)
    i = 0

    def repl(matchobj):
        # if src.lower().endswith('woff') or src.lower().endswith('ttf') or src.lower().endswith('otf') or src.lower().endswith('eot'):
        #     # dont handle font data uri currently
        #     return 'url(' + src + ')'
        nonlocal i
        i += 1
        print(i)
        return 'url('  ')'

    css = reg.sub(repl, css)
    print(css)


if __name__ == '__main__':
    test()

