#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retcon 壳 v0.3 —— 磨损按「段」定位，二分逼近。

一句话（原文）被机械切成 N 段（只按标点切，不按语义）。
每次使用记下「这次覆盖了哪几段」。没有覆盖到的段，就是磨损。

为什么是段：
    磨损不是「少了一点」这种模糊的东西 —— 它是具体的第 3 段、第 7 段。
    察觉到结论有问题 = 察觉到磨损的地方 = 二分到具体哪一段。

用法（零依赖）：
    python retcon.py <库> init
    python retcon.py <库> say --raw "原文……" --source "出处"
    python retcon.py <库> cover T1 --use u1 --reads "3,7"     # 这次用了第3、7段
    python retcon.py <库> wear  T1                            # 没被任何一次带走的段
    python retcon.py <库> bisect T1                           # 二分逼近磨损
    python retcon.py <库> show  T1
    python retcon.py <库> seams
    python retcon.py <库> check

设计约束：
1. 原文永不被写：任何操作只追加。
2. 切段规则是机械的（按标点），不是语义分类。
3. 磨损是算出来的（没被任何一次覆盖的段），不是选出来的。
"""

import json
import sys
import os
import re
import time

# 只按标点切：逗号/句号/问号/叹号/分号/冒号/换行/破折号
SPLIT_RE = re.compile(r'[，。！？；：\n、]+|——|--')
CJK = re.compile(r'[\u4e00-\u9fff]')


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def split_segments(raw):
    """机械切段：只按标点，不判断意思。短于 2 个汉字的碎片合并到前一段。"""
    parts = [p.strip() for p in SPLIT_RE.split(raw) if p.strip()]
    out = []
    for p in parts:
        if out and len(CJK.findall(p)) < 2:
            out[-1] = out[-1] + ' ' + p
        else:
            out.append(p)
    return out


class Store:
    def __init__(self, root):
        self.root = root
        self.texts = os.path.join(root, 'texts.jsonl')
        self.uses = os.path.join(root, 'uses.jsonl')
        self.seams = os.path.join(root, 'seams.jsonl')

    def init(self):
        os.makedirs(self.root, exist_ok=True)
        for p in (self.texts, self.uses, self.seams):
            if not os.path.exists(p):
                open(p, 'a', encoding='utf-8').close()
        return {'ok': True, 'msg': f'库已建：{self.root}'}

    def _read(self, path):
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def all_texts(self):
        return self._read(self.texts)

    def all_uses(self):
        return self._read(self.uses)

    def all_seams(self):
        return self._read(self.seams)

    def text(self, tid):
        hits = [t for t in self.all_texts() if t['id'] == tid]
        return hits[-1] if hits else None

    def append(self, path, rec):
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def seam(self, op, targets, before, after, reason=''):
        self.append(self.seams, {
            'id': f's_{int(time.time()*1000)}', 'ts': now(),
            'actor': 'user', 'op': op, 'targets': targets,
            'before': before, 'after': after, 'reason': reason,
        })


def parse_nums(s):
    out = []
    for x in (s or '').split(','):
        x = x.strip()
        if x.isdigit():
            out.append(int(x))
    return out


def cmd_init(store, args):
    return store.init()


def cmd_say(store, args):
    raw = (args.get('raw') or '').strip()
    if not raw:
        return {'ok': False, 'msg': 'say 要一句话原文（--raw）'}
    for t in store.all_texts():
        if t['raw'] == raw:
            return {'ok': True, 'msg': f'这句话已有：{t["id"]}（原文不改）', 'record': t, 'reuse': True}
    tid = args.get('id') or f'T{len({t["id"] for t in store.all_texts()})+1}'
    if store.text(tid):
        return {'ok': False, 'msg': f'{tid} 已存在'}
    segs = split_segments(raw)
    rec = {'id': tid, 'raw': raw, 'source': args.get('source', ''),
           'segments': [{'i': i + 1, 'text': s} for i, s in enumerate(segs)],
           'created': now()}
    store.append(store.texts, rec)
    store.seam('say', [tid], None, rec, f'建一句话，切成 {len(segs)} 段')
    return {'ok': True, 'msg': f'{tid} 已建，切成 {len(segs)} 段', 'record': rec}


def cmd_cover(store, args):
    """一次使用：--use u1 --reads 3,7（这次带走了哪几段）"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    uid = args.get('use') or f'{tid}_u{len([u for u in store.all_uses() if u["text_id"] == tid]) + 1}'
    nums = parse_nums(args.get('reads'))
    if not nums:
        return {'ok': False, 'msg': 'cover 必须写这次带走了哪几段（--reads 3,7）'}
    n = len(t['segments'])
    bad = [x for x in nums if x < 1 or x > n]
    if bad:
        return {'ok': False, 'msg': f'段号越界：{bad}（原文只有 {n} 段）'}
    ctx = (args.get('context') or '').strip()
    rec = {'id': uid, 'text_id': tid, 'context': ctx, 'reads': sorted(set(nums)), 'ts': now()}
    store.append(store.uses, rec)
    store.seam('cover', [tid, uid], None, rec,
               f'{uid} 带走第 {",".join(map(str, rec["reads"]))} 段')
    return {'ok': True, 'msg': f'{uid} 已记（带走 {len(rec["reads"])} 段）', 'record': rec}


def wear_of(store, t):
    """磨损 = 原文里从没被任何一次使用带走的段"""
    uses = [u for u in store.all_uses() if u['text_id'] == t['id']]
    covered = set()
    for u in uses:
        covered |= set(u['reads'])
    return [s for s in t['segments'] if s['i'] not in covered], uses


def cmd_wear(store, args):
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    worn, uses = wear_of(store, t)
    if not uses:
        return {'ok': True, 'msg': '还没被用过：没有覆盖，就没有磨损',
                '原文': t['raw'], '段数': len(t['segments']), '磨损段': []}
    return {
        'ok': True,
        '使用次数': len(uses),
        '磨损段（没被任何一次带走）': worn,
        '磨损段数': len(worn),
        '原文段数': len(t['segments']),
        '提示': '察觉结论有问题 = 察觉这些段里的某一段。用 bisect 二分定位。',
    }


def cmd_bisect(store, args):
    """二分逼近：默认先看整个区间，人回答这一半有没有问题，逐层缩到单段。"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    worn, uses = wear_of(store, t)
    if not worn:
        return {'ok': True, 'msg': '没有磨损段：原文被覆盖完整了', '磨损段': []}
    lo, hi = args.get('lo'), args.get('hi')
    segs = t['segments']
    left = [s for s in worn if s['i'] <= len(segs) // 2] if not (lo or hi) else [s for s in worn if int(lo) <= s['i'] <= int(hi)]
    # 无参数时：对整个磨损区间做第一次二分
    if not (lo or hi):
        mid = len(segs) // 2
        first = [s for s in worn if s['i'] <= mid]
        second = [s for s in worn if s['i'] > mid]
        return {'ok': True,
                'msg': '第一刀：把整段原文切成两半，磨损段分成左边和右边',
                '左边（第1段到第%d段）' % mid: first,
                '右边（第%d段到第%d段）' % (mid + 1, len(segs)): second,
                '怎么走': '察觉结论哪里不对，就先看哪一半有问题，再往那半二分。'
                          '带 --lo 3 --hi 7 缩到某个区间。'}
    return {'ok': True, '区间': f'{lo}-{hi}', '磨损段': left,
            '怎么走': '区间里还有多段，继续 --lo N --hi M 二分。'}


def cmd_show(store, args):
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': '找不到'}
    worn, uses = wear_of(store, t)
    worn_i = {s['i'] for s in worn}
    segs = [{'i': s['i'], 'text': s['text'], '磨损': s['i'] in worn_i}
            for s in t['segments']]
    return {'ok': True, '原文': t['raw'], '段': segs, '使用次数': len(uses)}


def cmd_seams(store, args):
    n = int(args.get('tail', 10))
    return {'ok': True, 'seams': store.all_seams()[-n:]}


def cmd_check(store, args):
    errs = []
    tid = {t['id'] for t in store.all_texts()}
    for u in store.all_uses():
        if u['text_id'] not in tid:
            errs.append(f'{u["id"]}: 挂在不存在的句子 {u["text_id"]} 上')
    for t in store.all_texts():
        if not t.get('segments'):
            errs.append(f'{t["id"]}: 没有切段')
    return {'ok': not errs, 'msg': f'{len(tid)} 句话、{len(store.all_uses())} 次使用、{len(errs)} 个问题',
            '问题': errs}


def parse(argv):
    cmd = argv[0] if argv else 'help'
    args, rest, i = {}, [], 1
    while i < len(argv):
        a = argv[i]
        if a.startswith('--'):
            k = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                args[k] = argv[i + 1]
                i += 2
            else:
                args[k] = True
                i += 1
        else:
            rest.append(a)
            i += 1
    if rest:
        args['id'] = rest[0]
    return cmd, args


CMDS = {'init': cmd_init, 'say': cmd_say, 'cover': cmd_cover,
        'wear': cmd_wear, 'bisect': cmd_bisect, 'show': cmd_show,
        'seams': cmd_seams, 'check': cmd_check}


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[1] == 'help':
        print(__doc__)
        return 0
    root = argv[0]
    cmd, args = parse(argv[1:])
    if cmd not in CMDS:
        print(f'未知命令：{cmd}')
        return 2
    store = Store(root)
    if cmd != 'init' and not os.path.exists(store.texts):
        store.init()
    res = CMDS[cmd](store, args)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
