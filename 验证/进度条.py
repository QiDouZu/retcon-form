# -*- coding: utf-8 -*-
"""进度条.py —— 把这些猜想的验证进度，画成一眼能看的条。

    python 进度条.py                 # 终端 / markdown 文本进度条
    python 进度条.py --json          # 只输出汇总 JSON（给别的地方接）
    python 进度条.py --out x.md      # 写到文件（README 可直接贴）

数据来源只有两处：

  验证/_结果.json     —— 猜想清单（未验的在这里）
  验证/结果/*.json    —— 测试者的结果（一个测试一个文件）
  验证/结果/*.md      —— 也认，按 _模板.md 的格式读（「猜想编号：C1」「结论：支持」）

规矩：**没验就是没验。** 进度条不把"我们相信"算成"支持"。
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLAIMS = os.path.join(HERE, '_结果.json')
RESULTS = os.path.join(HERE, '结果')

VERDICTS = ('支持', '推翻', '部分')
BAR_LEN = 20


def load_claims():
    if not os.path.exists(CLAIMS):
        return []
    with io.open(CLAIMS, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('claims') or []


def norm_verdict(v):
    v = (v or '').strip()
    if '推' in v or '否' in v or '反' in v:
        return '推翻'
    if '部分' in v or '一半' in v or '一半' in v:
        return '部分'
    if '支' in v or '是' in v or '对' in v or '成' in v:
        return '支持'
    return None


def iter_result_files():
    files = []
    for pat in ('*.json', '*.md'):
        files.extend(glob.glob(os.path.join(RESULTS, pat)))
    return sorted(files)


def read_json_result(path):
    try:
        # utf-8-sig：Windows 记事本/PowerShell 写出的 JSON 常带 BOM，json.load 读不了
        with io.open(path, 'r', encoding='utf-8-sig') as f:
            d = json.load(f)
    except Exception:
        return None
    claim = (d.get('claim') or d.get('id') or '').strip()
    verdict = norm_verdict(d.get('verdict') or d.get('conclusion') or '')
    if not claim or not verdict:
        return None
    return {
        'claim': claim.upper() if claim.upper().startswith('C') else claim,
        'verdict': verdict,
        'by': d.get('by') or d.get('author') or '匿名',
        'note': d.get('note') or d.get('summary') or '',
        'file': os.path.basename(path),
    }


def read_md_result(path):
    try:
        with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return None
    m = re.search(r'猜想编号[:：]\s*(C\d+)', text)
    claim = m.group(1) if m else ''
    m2 = re.search(r'结论[:：]\s*([^\n]+)', text)
    verdict = norm_verdict(m2.group(1)) if m2 else None
    m3 = re.search(r'署名[:：]\s*([^\n]+)', text)
    by = m3.group(1).strip() if m3 else '匿名'
    if not claim or not verdict:
        return None
    return {'claim': claim, 'verdict': verdict, 'by': by,
            'note': '', 'file': os.path.basename(path)}


def load_tests():
    out = []
    for path in iter_result_files():
        r = read_json_result(path) if path.endswith('.json') else read_md_result(path)
        if r:
            out.append(r)
    return out


def bar(ratio, width=BAR_LEN):
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return '█' * filled + '░' * (width - filled)


def build(claims, tests):
    """算出每条猜想的票数与整体状态。规则：
    支持票占多数 → 支持；推翻票占多数 → 推翻；都有但不占多数 → 争议；一半对一半 → 争议；
    没有任何测试 → 未验。
    """
    by_claim = {}
    for t in tests:
        by_claim.setdefault(t['claim'], []).append(t)

    rows = []
    for c in claims:
        ts = by_claim.get(c['id'], [])
        sup = sum(1 for t in ts if t['verdict'] == '支持')
        ref = sum(1 for t in ts if t['verdict'] == '推翻')
        par = sum(1 for t in ts if t['verdict'] == '部分')
        total = len(ts)
        if total == 0:
            status = '未验'
        elif ref > sup + par:
            status = '推翻'
        elif sup > ref + par:
            status = '支持'
        elif sup + par > ref:
            status = '倾向支持'
        else:
            status = '争议'
        # 进度条的含义：**被证实的比例**（推翻=0，支持=1，部分=0.5）。
        # 没有测试时是 0 —— 不把"我们相信"画成满格。
        score = (sup * 1.0 + par * 0.5) / total if total else 0.0
        rows.append({**c, 'sup': sup, 'ref': ref, 'par': par,
                     'total': total, 'status': status, 'score': score})

    done = sum(1 for r in rows if r['total'] > 0)
    return {
        'updated': time.strftime('%Y-%m-%d'),
        'claims_total': len(rows),
        'claims_tested': done,
        'tests_total': len(tests),
        'rows': rows,
    }


def render_text(summary):
    lines = []
    lines.append('# 猜想验证进度')
    lines.append('')
    if summary['claims_total'] == 0:
        return '（没有猜想清单：先补 验证/_结果.json）\n'
    lines.append('> 进度条 = **被证实的比例**。支持 = 满格，部分 = 半格，推翻 = 空格。')
    lines.append('> 没验就是没验 —— 空着不是"差不多"，是"还什么都不知道"。')
    lines.append('')
    lines.append('**%d 条猜想 / 已收到 %d 条测试 / %d 条有结果**'
                 % (summary['claims_total'], summary['tests_total'], summary['claims_tested']))
    lines.append('')
    lines.append('| 猜想 | 状态 | 进度 | 支持/部分/推翻 |')
    lines.append('|---|---|---|---|')
    for r in summary['rows']:
        lines.append('| %s %s | %s | `%s` | %d / %d / %d |'
                     % (r['id'], r['text'], r['status'], bar(r['score']),
                        r['sup'], r['par'], r['ref']))
    lines.append('')
    lines.append('*更新于 %s —— 这条是脚本生成的，别手改。*' % summary['updated'])
    return '\n'.join(lines) + '\n'


def main():
    # Windows 控制台默认 GBK，进度条字符（█░）会炸 —— 统一按 UTF-8 输出。
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true', help='只输出汇总 JSON')
    ap.add_argument('--out', default='', help='写到指定文件（默认 stdout）')
    args = ap.parse_args()

    claims = load_claims()
    tests = load_tests()
    summary = build(claims, tests)

    if args.json:
        text = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        text = render_text(summary)

    if args.out:
        with io.open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        print('written: %s' % args.out)
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
