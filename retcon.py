#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retcon 壳 v0.2 —— 单位是「同一句话的多次使用」。

一句话（原文）被反复使用。每一次使用，都是一次覆盖：
    1. 它原本的语义被磨损（磨掉的是这次没用上的部分）
    2. 背景给它补上新的东西（这次用出来的部分）
    3. 你不可能完全覆盖它 —— 多出来的差，就是研究的对象

所以核心不是「逻辑」「表象」「变体」，是：
    同一句话 + N 次使用 + 每次读出的东西
    交集  = 相同的地方（让人研究的入口，反复稳定的意思）
    差集  = 覆盖不到的部分（研究点本身）
    磨损  = 只在早期出现过、后来不再出现的读法

用法（零依赖）：
    python retcon.py <库目录> init
    python retcon.py <库目录> say --raw "写不出推翻条件就别写" --source "10-25 对话"
    python retcon.py <库目录> use T1 --context "自检时" --read "拦废话,拦表演"
    python retcon.py <库目录> use T1 --context "教别人时" --read "拦废话,教不会的人"
    python retcon.py <库目录> cover T1
    python retcon.py <库目录> texts
    python retcon.py <库目录> seams [--tail 10]
    python retcon.py <库目录> check
"""

import json
import sys
import os
import time

STATE_NEW = '生'      # 0 次使用：还没有被用过，没有被覆盖，没有差集
STATE_USED = '用'     # ≥1 次使用
STATE_SAT = '饱和'    # 连续两次使用不再产生新读法

OPS = {'say', 'use', 'seam'}


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


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
        # 同一 id 取最后一条（状态会被新版本覆盖，原文不动）
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


def split_reads(s):
    return [x.strip() for x in (s or '').split(',') if x.strip()]


def cmd_init(store, args):
    return store.init()


def cmd_say(store, args):
    raw = (args.get('raw') or '').strip()
    if not raw:
        return {'ok': False, 'msg': 'say 要一句话原文（--raw）'}
    # 同一句话只建一次：原文一模一样就复用
    for t in store.all_texts():
        if t['raw'] == raw:
            return {'ok': True, 'msg': f'这句话已有：{t["id"]}（原文不改）', 'record': t, 'reuse': True}
    tid = args.get('id') or f'T{len(store.all_texts())+1}'
    if store.text(tid):
        return {'ok': False, 'msg': f'{tid} 已存在'}
    rec = {'id': tid, 'raw': raw, 'source': args.get('source', ''),
           'state': STATE_NEW, 'created': now()}
    store.append(store.texts, rec)
    store.seam('say', [tid], None, rec, '建一句话')
    return {'ok': True, 'msg': f'{tid} 已建：{raw[:30]}', 'record': rec}


def cmd_use(store, args):
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    reads = split_reads(args.get('read'))
    if not reads:
        return {'ok': False, 'msg': 'use 必须写这次读出了什么（--read，逗号分隔）'}
    ctx = (args.get('context') or '').strip()
    if not ctx:
        return {'ok': False, 'msg': 'use 必须写背景（--context）——没有背景就没有覆盖'}
    uses = [u for u in store.all_uses() if u['text_id'] == tid]
    uid = f'{tid}_u{len(uses)+1}'
    before = set()
    for u in uses:
        before |= set(u['reads'])
    new_reads = [r for r in reads if r not in before]
    rec = {'id': uid, 'text_id': tid, 'context': ctx,
           'reads': reads, 'new': new_reads, 'ts': now()}
    store.append(store.uses, rec)

    # 状态：用过 ≥1 次 = 用；连续两次无新增 = 饱和
    state = STATE_USED
    if uses:
        last_new = uses[-1].get('new') or []
        if not new_reads and not last_new:
            state = STATE_SAT
    t2 = dict(t)
    t2['state'] = state
    store.append(store.texts, t2)
    store.seam('use', [tid, uid], None, rec,
               f'第{len(uses)+1}次使用；新增{len(new_reads)}条')
    return {'ok': True, 'msg': f'{tid} 第{len(uses)+1}次使用（背景：{ctx}）',
            'record': rec, 'text_state': state}


def cmd_cover(store, args):
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    uses = [u for u in store.all_uses() if u['text_id'] == tid]
    if not uses:
        return {'ok': True, 'text': t['raw'], 'msg': '这句话还没被用过：没有覆盖，也没有差集',
                '使用次数': 0, '研究点': [], '相同的地方': []}
    sets = [set(u['reads']) for u in uses]
    union = set().union(*sets)
    inter = set.intersection(*sets) if len(sets) > 1 else set()
    every_seen = union
    # 磨损：只在早期出现、最后一次之后不再出现
    worn = []
    if len(uses) > 1:
        last = set(uses[-1]['reads'])
        for r in union:
            if r not in last:
                appeared_at = [i for i, u in enumerate(uses) if r in u['reads']]
                if appeared_at and max(appeared_at) < len(uses) - 1:
                    worn.append(r)
    return {
        'ok': True,
        'text': t['raw'],
        '使用次数': len(uses),
        '相同的地方（交集）': sorted(inter),
        '多出来的（每次独有）': {u['id']: [r for r in u['reads'] if r not in inter] for u in uses},
        '差集（研究点）': sorted(union - inter),
        '磨损（只在早期出现）': worn,
        '状态': t['state'],
        '说明': '交集=反复稳定的意思；差集=覆盖不到的部分；磨损=这次用掉了的老意思',
    }


def cmd_texts(store, args):
    rows = []
    for t in store.all_texts():
        n = len([u for u in store.all_uses() if u['text_id'] == t['id']])
        rows.append({'id': t['id'], 'raw': t['raw'], '使用次数': n, '状态': t['state']})
    return {'ok': True, 'texts': rows}


def cmd_seams(store, args):
    n = int(args.get('tail', 10))
    return {'ok': True, 'seams': store.all_seams()[-n:]}


def cmd_check(store, args):
    errs = []
    tid = {t['id'] for t in store.all_texts()}
    for u in store.all_uses():
        if u['text_id'] not in tid:
            errs.append(f'{u["id"]}: 挂在不存在的句子 {u["text_id"]} 上')
        if not u.get('reads'):
            errs.append(f'{u["id"]}: 没有任何读法')
    return {'ok': not errs,
            'msg': f'{len(tid)} 句话、{len(store.all_uses())} 次使用、{len(errs)} 个问题',
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


CMDS = {'init': cmd_init, 'say': cmd_say, 'use': cmd_use,
        'cover': cmd_cover, 'texts': cmd_texts,
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
