#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retcon 壳 v0.4 —— 段定位磨损 + 分离单一变量 + 过程可监控 + 结果可反推。

一句话（原文）被机械切成 N 段（只按标点切，不按语义）。
每次使用记下「这次覆盖了哪几段」。没有覆盖到的段，就是磨损。
磨损里一段一段分开研究 —— 一次只研究一个变量，研究完再换下一个。

用法（零依赖）：
    python retcon.py <库> init
    python retcon.py <库> say --raw "原文……" --source "出处"
    python retcon.py <库> cover T1 --reads "1,2,3" --context "写 SHAPE 时"
    python retcon.py <库> vars  T1                    # 分离：每段一个变量，看哪些还没研究
    python retcon.py <库> study T1 --seg 5 --finding "这一段我之前完全没带走" --next "去看原文第5段"
    python retcon.py <库> wear  T1                    # 还没被任何一次带走的段
    python retcon.py <库> bisect T1                   # 二分逼近（--lo --hi 缩区间）
    python retcon.py <库> trace T1 --segs 5,6         # 反推：这个结论由哪几次使用支撑、哪天写的
    python retcon.py <库> monitor T1                  # 过程监控：这条判断一路怎么走过来的
    python retcon.py <库> show  T1
    python retcon.py <库> check

设计约束：
1. 原文永不被写：任何操作只追加。
2. 切段规则是机械的（按标点），不是语义分类。
3. 磨损是算出来的（没被任何一次覆盖的段），不是选出来的。
4. 一次只研究一段（单一变量）：study 必须指定 --seg，不许写「整体上」。
5. 过程可监控：每次操作都落一条缝，缝可回放。
6. 结果可反推：任何结论必须能反推回它的段号与缝。
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
        self.studies = os.path.join(root, 'studies.jsonl')
        self.seams = os.path.join(root, 'seams.jsonl')

    def init(self):
        os.makedirs(self.root, exist_ok=True)
        for p in (self.texts, self.uses, self.studies, self.seams):
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

    def all_studies(self):
        return self._read(self.studies)

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


def cmd_vars(store, args):
    """分离单一变量：一段 = 一个变量。列表上每段只有三个状态。"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    worn, uses = wear_of(store, t)
    worn_i = {s['i'] for s in worn}
    studied = {}
    for st in store.all_studies():
        if st['text_id'] == tid:
            studied.setdefault(st['seg'], []).append(st)
    rows = []
    for s in t['segments']:
        i = s['i']
        if i in studied:
            state = '已研究'
        elif i in worn_i:
            state = '磨损待研究'
        else:
            state = '已被带走'
        rows.append({'段': i, 'text': s['text'], '状态': state,
                     '研究次数': len(studied.get(i, []))})
    todo = [r for r in rows if r['状态'] == '磨损待研究']
    return {'ok': True, '变量数': len(rows), '还没研究的': len(todo),
            '变量': rows,
            '下一步': f'一次只研究一段。挑第一段磨损：python retcon.py <库> study {tid} --seg {todo[0]["段"]} --finding "…"' if todo else '全部变量都已处理（带走或研究过）。'}


def cmd_study(store, args):
    """研究单一变量：一次只许一段。--next 不给就等于没往下推。"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    seg = args.get('seg')
    if not seg or not str(seg).isdigit():
        return {'ok': False, 'msg': 'study 必须指定 --seg N（一次只研究一个变量）'}
    seg = int(seg)
    n = len(t['segments'])
    if seg < 1 or seg > n:
        return {'ok': False, 'msg': f'段号 {seg} 越界（原文 {n} 段）'}
    finding = (args.get('finding') or '').strip()
    if not finding:
        return {'ok': False, 'msg': 'study 必须写这次研究出了什么（--finding）'}
    sid = f'{tid}_s{len([x for x in store.all_studies() if x["text_id"] == tid]) + 1}'
    rec = {'id': sid, 'text_id': tid, 'seg': seg, 'finding': finding,
           'next': (args.get('next') or '').strip(), 'ts': now()}
    store.append(store.studies, rec)
    seg_text = [s['text'] for s in t['segments'] if s['i'] == seg][0]
    store.seam('study', [tid, sid], None, rec,
               f'研究第{seg}段「{seg_text[:20]}」')
    return {'ok': True, 'msg': f'第{seg}段已研究：{finding[:40]}',
            'record': rec,
            '下一段': rec['next'] or '（没写下一步：这次研究没接上任何东西）'}


def cmd_trace(store, args):
    """结果可反推：这组段号当初是被哪几次使用带走的、哪天、谁动的。"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    segs = parse_nums(args.get('segs'))
    if not segs:
        return {'ok': False, 'msg': 'trace 必须给 --segs 5,6（要反推的段号）'}
    uses = [u for u in store.all_uses() if u['text_id'] == tid]
    studies = [s for s in store.all_studies() if s['text_id'] == tid]
    sources = []
    for u in uses:
        hit = sorted(set(segs) & set(u['reads']))
        if hit:
            sources.append({'使用': u['id'], '背景': u['context'],
                            '带走的段': hit, '时间': u['ts']})
    seg_texts = {s['i']: s['text'] for s in t['segments']}
    return {
        'ok': True,
        '反推目标段': [{'段': i, 'text': seg_texts.get(i, '')} for i in segs],
        '由哪几次使用支撑': sources,
        '研究记录': [s for s in studies if s['seg'] in segs],
        '原文': t['raw'],
        '提示': '如果某个段没有任何使用支撑，说明它是「事后才被发现的」——那正是磨损。',
    }


def cmd_monitor(store, args):
    """过程可监控：这条判断一路的操作流水（缝），按时间顺排。"""
    tid = args.get('id')
    t = store.text(tid)
    if not t:
        return {'ok': False, 'msg': f'找不到 {tid}'}
    seams = [s for s in store.all_seams() if tid in (s.get('targets') or [])]
    # 按时间排序（seam id 里带毫秒）
    seams.sort(key=lambda s: s['id'])
    return {'ok': True, '操作数': len(seams),
            '流水': [{'时间': s['ts'], '动作': s['op'],
                      '内容': s['reason'] or s['after']} for s in seams],
            '原文': t['raw']}


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
        'vars': cmd_vars, 'study': cmd_study, 'trace': cmd_trace,
        'monitor': cmd_monitor,
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
