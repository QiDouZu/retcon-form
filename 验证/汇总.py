# -*- coding: utf-8 -*-
"""汇总.py —— 把 结果/ 里所有投稿，汇成一页「他人经验.md」。

    python 验证/汇总.py

这是「别人走我们猜想的那条路」的集合页。每次有新投稿 → 重跑 → 页面实时变。

读两种格式：`.json`（claim/verdict/by/note/condition/date）与 `.md`（照 _模板.md）。
写出的 `他人经验.md` 是生成物，**别手改**。

投稿机制见 投稿.md；进度条见 进度条.py（管票数，这页管故事）。
"""
import glob
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, '结果')
OUT = os.path.join(HERE, '他人经验.md')


def read_json(path):
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as f:
            d = json.load(f)
    except Exception:
        return None
    claim = (d.get('claim') or d.get('id') or '').strip()
    if not claim:
        return None
    return {
        'claim': claim.upper() if claim.upper().startswith('C') else claim,
        'verdict': (d.get('verdict') or d.get('conclusion') or '未填').strip(),
        'by': (d.get('by') or d.get('author') or '匿名').strip(),
        'note': (d.get('note') or d.get('summary') or '').strip(),
        'condition': (d.get('condition') or d.get('situation') or '').strip(),
        'date': (d.get('date') or '').strip(),
        'file': os.path.basename(path),
    }


def read_md(path):
    try:
        with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return None
    m = re.search(r'猜想编号[:：]\s*(C\d+)', text)
    claim = m.group(1) if m else ''
    if not claim:
        return None
    verdict = ''
    m2 = re.search(r'结论[:：]\s*([^\n]+)', text)
    if m2:
        verdict = m2.group(1).strip()
    by = '匿名'
    m3 = re.search(r'署名[:：]\s*([^\n]+)', text)
    if m3:
        by = m3.group(1).strip()
    # 「怎么验的」和「什么情况下不成立」取整段
    def section(key):
        m = re.search(r'##[^\n]*' + key + r'[^\n]*\n+([\s\S]*?)(?=\n## |\Z)', text)
        return m.group(1).strip() if m else ''
    return {
        'claim': claim,
        'verdict': verdict or '未填',
        'by': by,
        'note': section('怎么验的') or section('怎样验的') or section('怎么验'),
        'condition': section('不成立'),
        'date': '',
        'file': os.path.basename(path),
    }


def load():
    items = []
    for pat in ('*.json', '*.md'):
        for path in sorted(glob.glob(os.path.join(RESULTS, pat))):
            r = read_json(path) if path.endswith('.json') else read_md(path)
            if r:
                items.append(r)
    return items


def render(items):
    lines = ['# 他人经验', '']
    lines.append('> **这是「别人走我们猜想的经验」的集合页，每次有人投稿就重跑更新。**')
    lines.append('> 投稿方式见 [投稿.md](投稿.md)。这页是生成的，别手改。')
    lines.append('')
    if not items:
        lines.append('**还没有投稿。** 空着是对的——等第一个走这条路的人。')
        lines.append('')
        lines.append('[去验一条 →](投稿.md)')
        lines.append('')
        lines.append('*生成于 %s —— 还没有人投稿，这行就是证据。*' % time.strftime('%Y-%m-%d'))
        return '\n'.join(lines) + '\n'

    lines.append('**共 %d 条经验，来自 %d 位测试者。**' % (
        len(items), len({i['by'] for i in items})))
    lines.append('')
    lines.append('| 猜想 | 结果 | 验的人 | 怎么验的 | 什么情况下不成立 |')
    lines.append('|---|---|---|---|---|')
    for i in items:
        note = (i['note'] or '').replace('\n', ' ').replace('|', '/')[:120]
        cond = (i['condition'] or '').replace('\n', ' ').replace('|', '/')[:120]
        lines.append('| %s | %s | %s | %s | %s |' % (
            i['claim'], i['verdict'], i['by'], note or '（没写）', cond or '**没写——这是不合格投稿**'))
    lines.append('')
    lines.append('> 最后一列是空的投稿，按规矩不算数：**没写清「什么情况下不成立」的，等于只说了"我相信"。**')
    lines.append('')
    lines.append('*生成于 %s。投稿进 `结果/`，重跑 `python 验证/汇总.py` 更新本页。*' % time.strftime('%Y-%m-%d'))
    return '\n'.join(lines) + '\n'


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    items = load()
    text = render(items)
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('written: %s  (%d 条投稿)' % (OUT, len(items)))


if __name__ == '__main__':
    main()
