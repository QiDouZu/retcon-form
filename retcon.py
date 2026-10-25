#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retcon 执行壳 v0.1 —— 五种记录 + 缝 + 三个查询。零依赖，一个目录一个库。

用法：
    python retcon.py <库目录> init
    python retcon.py <库目录> surface  --source "BV11jnm6bENb 4帧" --logics L1,L2
    python retcon.py <库目录> logic    --id L1 --surface L1_surface
    python retcon.py <库目录> done     L1 --text "我以为这是账本不是时间"
    python retcon.py <库目录> doing    L1 --text "被当成时间才是议题"
    python retcon.py <库目录> challenge L1 --note "取12帧验"
    python retcon.py <库目录> variant  --logic L1 --id V1_并列十二坑
    python retcon.py <库目录> close    L1 --reason "无新变体"
    python retcon.py <库目录> reopen   L1 --reason "新证据"
    python retcon.py <库目录> q1       <surface_id>
    python retcon.py <库目录> q2       <variant_id>
    python retcon.py <库目录> q3       <surface_id>
    python retcon.py <库目录> check
    python retcon.py <库目录> show     <id>
    python retcon.py <库目录> seams    [--tail 10]

设计约束（写死在代码里，不进文档）：
1. 原文永不被写：任何操作只追加，不改旧行。改写 = 拒绝。
2. 任何结论不许自立为事实：derived 必须带来源坐标。
3. 合并只允许「相同点」：产物是一条 derived 记录，原文不动。不同点不允许合并。
4. 没有权重、没有评分、没有标签、没有相似度。

缝是 append-only 的链，回根 = 沿缝逆序回溯。
"""

import json
import sys
import os
import time

STATE_EMPTY = '空'
STATE_HALF = '单栏'
STATE_BOTH = '双栏齐备'
STATE_TEST = '被测试'
STATE_CLOSED = '封闭'
STATE_TOMB = '墓碑'

# 唯一允许的状态迁移： (from, op, to)
TRANSITIONS = {
    ('空', 'write_done', '单栏'),
    ('单栏', 'write_doing', '双栏齐备'),
    ('双栏齐备', 'challenge', '被测试'),
    ('被测试', 'spawn_variant', '被测试'),
    ('被测试', 'close', '封闭'),
    ('封闭', 'reopen', '被测试'),
}

LEGAL_OPS = {
    'create', 'amend_done', 'amend_doing', 'challenge', 'spawn_variant',
    'kill', 'close', 'reopen', 'compress', 'juxtapose', 'merge_same',
}

KINDS = {'surface', 'logic', 'variant', 'seam', 'compress'}


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


class Store:
    def __init__(self, root):
        self.root = root
        self.records_path = os.path.join(root, 'records.jsonl')
        self.seams_path = os.path.join(root, 'seams.jsonl')

    def init(self):
        os.makedirs(self.root, exist_ok=True)
        for p in (self.records_path, self.seams_path):
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

    def records(self):
        return self._read(self.records_path)

    def seams(self):
        return self._read(self.seams_path)

    def by_id(self, rid):
        for r in self.records():
            if r.get('id') == rid:
                return r
        return None

    # ── 追加即真相 ──
    def append_record(self, rec):
        with open(self.records_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def append_seam(self, seam):
        with open(self.seams_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(seam, ensure_ascii=False) + '\n')


def new_seam(actor, op, targets, before, after, reason=''):
    return {
        'id': f'seam_{int(time.time()*1000)}',
        'ts': now(),
        'actor': actor,
        'op': op,
        'targets': targets,
        'before': before,
        'after': after,
        'reason': reason,
    }


def cmd_init(store, args):
    return store.init()


def get_or_fail(store, rid, kind=None):
    # ⚠ 取当前版本（同 id 最后一条），不是第一条——状态机只认最新态
    r = _current(store, rid)
    if not r:
        return None, f'找不到 {rid}'
    if kind and r.get('kind') != kind:
        return None, f'{rid} 是 {r.get("kind")}，不是 {kind}'
    return r, None


def cmd_surface(store, args):
    sid = args.get('id') or f'surf_{int(time.time()*1000)}'
    logics = [x.strip() for x in (args.get('logics') or '').split(',') if x.strip()]
    if not args.get('source'):
        return {'ok': False, 'msg': 'surface 的 source（原文坐标）必填'}
    rec = {'id': sid, 'kind': 'surface', 'source': args['source'],
           'logics': logics, 'created': now()}
    store.append_record(rec)
    store.append_seam(new_seam('user', 'create', [sid], None, rec, '建表象'))
    return {'ok': True, 'msg': f'表象 {sid} 已建（逻辑 {len(logics)} 条）', 'record': rec}


def cmd_logic(store, args):
    lid = args.get('id') or f'L{int(time.time()*1000)}'
    sid = args.get('surface')
    if not sid:
        return {'ok': False, 'msg': 'logic 必须挂在一个 surface 上'}
    sur, err = get_or_fail(store, sid, 'surface')
    if err:
        return {'ok': False, 'msg': err}
    if store.by_id(lid):
        return {'ok': False, 'msg': f'{lid} 已存在（原文不覆盖）'}
    rec = {'id': lid, 'kind': 'logic', 'surface_id': sid,
           'produced_from': args.get('produced_from'),
           'done': None, 'doing': None, 'variants': [],
           'state': STATE_EMPTY, 'created': now()}
    store.append_record(rec)
    # 挂到 surface 上：只追加一条 surface 更新记录？——不行，原文不写。
    # 做法：surface.logics 是派生视图，由 q1 按 surface_id 反查算出来。
    store.append_seam(new_seam('user', 'create', [lid], None, rec, '建逻辑'))
    return {'ok': True, 'msg': f'逻辑 {lid} 已建（空状态）', 'record': rec}


def _set_field(store, rec, field, value, op):
    """只追加新行（同 id 的新版本），不回写旧行。旧行靠 seq 顺序胜出。"""
    new = dict(rec)
    new[field] = value
    new['seq'] = len(store.records())  # 版本序
    store.append_record(new)
    return new


def _current(store, rid):
    """同 id 取最后一条（版本序）"""
    hits = [r for r in store.records() if r.get('id') == rid]
    return hits[-1] if hits else None


def migrate(store, rec, op, to_state, note=''):
    cur = rec.get('state')
    if (cur, op, to_state) not in TRANSITIONS:
        return {'ok': False, 'msg': f'非法迁移：{cur} --{op}--> {to_state}'}
    new = _set_field(store, rec, 'state', to_state, op)
    store.append_seam(new_seam('user', op, [rec['id']], cur, to_state, note))
    return {'ok': True, 'msg': f'{rec["id"]}：{cur} → {to_state}', 'record': new}


def _logics_of(store, sid):
    """属于某个表象的全部逻辑（按 id 去重，取当前版本）"""
    seen = {}
    for r in store.records():
        if r.get('kind') == 'logic' and r.get('surface_id') == sid:
            seen[r['id']] = r
    return [_current(store, i) for i in seen]


def cmd_done(store, args):
    rec, err = get_or_fail(store, args['id'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    if not args.get('text'):
        return {'ok': False, 'msg': '完成时这一栏必须有字，不许空着'}
    if rec['state'] == STATE_EMPTY:
        new = _set_field(store, rec, 'done', args['text'], 'amend_done')
        new = _set_field(store, new, 'state', STATE_HALF, 'amend_done')
        store.append_seam(new_seam('user', 'amend_done', [rec['id']], None, args['text'], '写完成时 → 单栏'))
        return {'ok': True, 'msg': '完成时已写（单栏=非法态，必须再写进行时）', 'record': new}
    return {'ok': False, 'msg': '完成时只写一次（原文不改）'}


def cmd_doing(store, args):
    rec, err = get_or_fail(store, args['id'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    if not args.get('text'):
        return {'ok': False, 'msg': '进行时这一栏必须有字'}
    if rec.get('state') != STATE_HALF:
        return {'ok': False, 'msg': f'当前 {rec.get("state")}，只有「单栏」才能写进行时'}
    new = _set_field(store, rec, 'doing', args['text'], 'amend_doing')
    new = _set_field(store, new, 'state', STATE_BOTH, 'amend_doing')
    store.append_seam(new_seam('user', 'amend_doing', [rec['id']], None, args['text'], '写进行时 → 双栏齐备'))
    return {'ok': True, 'msg': '双栏齐备（这才是真正可封存的状态）', 'record': new}


def cmd_challenge(store, args):
    rec, err = get_or_fail(store, args['id'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    return migrate(store, rec, 'challenge', STATE_TEST, args.get('note', ''))


def cmd_variant(store, args):
    rec, err = get_or_fail(store, args['logic'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    if rec['state'] not in (STATE_TEST,):
        return {'ok': False, 'msg': f'只有「被测试」能产变体，现在是 {rec["state"]}'}
    vid = args.get('id') or f'V{int(time.time()*1000)}'
    vrec = {'id': vid, 'kind': 'variant', 'logic_id': args['logic'],
            'born_at_seq': len(store.records()), 'killed_by': args.get('killed_by'),
            'created': now()}
    store.append_record(vrec)
    cur = _current(store, rec['id'])
    vs = list(cur.get('variants') or []) + [vid]
    new = _set_field(store, cur, 'variants', vs, 'spawn_variant')
    store.append_seam(new_seam('user', 'spawn_variant', [rec['id'], vid], None, vid, '产出变体'))
    return {'ok': True, 'msg': f'{rec["id"]} 产出变体 {vid}', 'record': new, 'variant': vrec}


def cmd_close(store, args):
    rec, err = get_or_fail(store, args['id'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    if not args.get('reason'):
        return {'ok': False, 'msg': '封闭必须写 reason（医生：三种 op 必填 reason）'}
    return migrate(store, rec, 'close', STATE_CLOSED, args['reason'])


def cmd_reopen(store, args):
    rec, err = get_or_fail(store, args['id'], 'logic')
    if err:
        return {'ok': False, 'msg': err}
    if not args.get('reason'):
        return {'ok': False, 'msg': 'reopen 必须写 reason'}
    return migrate(store, rec, 'reopen', STATE_TEST, args['reason'])


def cmd_merge_same(store, args):
    """合并相同点：产物是 derived，原文一条不动。这正是用户要的「合并的是相同的地方」。"""
    ids = [x.strip() for x in (args.get('ids') or '').split(',') if x.strip()]
    if len(ids) < 2:
        return {'ok': False, 'msg': 'merge_same 至少两条'}
    recs = []
    for rid in ids:
        r, err = get_or_fail(store, rid)
        if err:
            return {'ok': False, 'msg': err}
        recs.append(r)
    mid = args.get('id') or f'M{int(time.time()*1000)}'
    mrec = {'id': mid, 'kind': 'variant', 'logic_id': None,
            'derived_from': ids, 'born_at_seq': len(store.records()),
            'killed_by': None, 'created': now(),
            'note': '相同点合并（交集视图），原文保留'}
    store.append_record(mrec)
    store.append_seam(new_seam('user', 'merge_same', ids + [mid], None, mid, '合并相同点'))
    return {'ok': True, 'msg': f'相同点合成 {mid}（derived，原文不动）', 'record': mrec}


def cmd_q1(store, args):
    sid = args['id']
    sur, err = get_or_fail(store, sid, 'surface')
    if err:
        return {'ok': False, 'msg': err}
    logics = _logics_of(store, sid)
    # 每个逻辑的变体集合（取当前版本）
    cur = {}
    for L in logics:
        cur[L['id']] = L
    sets = {}
    for lid, L in cur.items():
        vs = set(L.get('variants') or [])
        if vs:
            sets[lid] = vs
    if not sets:
        return {'ok': True, 'msg': '这个表象下还没有变体，Q1 只对已有变体做差集'}
    union = set().union(*sets.values())
    inter = set.intersection(*sets.values()) if len(sets) > 1 else set()
    diff = union - inter
    return {'ok': True, 'msg': 'Q1：相同点（交集）+ 多出来的部分（差集）',
            '相同点': sorted(inter),
            '差集': sorted(diff),
            '各逻辑': {k: sorted(v) for k, v in sets.items()},
            '说明': '相同点 = 让人研究的；差集 = 边界。两个都算，不丢'}


def cmd_q2(store, args):
    vid = args['id']
    v = store.by_id(vid)
    if not v:
        return {'ok': False, 'msg': f'找不到 {vid}'}
    # 找 op=spawn_variant 的缝，targets 含该变体
    hits = [s for s in store.seams() if s.get('op') == 'spawn_variant' and vid in s.get('targets', [])]
    if not hits:
        return {'ok': True, 'msg': f'{vid} 没有对应的推翻缝（它可能不是被推翻产出的）', '能kill的': []}
    victim_logics = []
    for s in hits:
        for t in s['targets']:
            if t != vid:
                victim_logics.append(t)
    return {'ok': True, 'msg': f'{vid} 来自推翻，能kill到 {len(set(victim_logics))} 个逻辑',
            '能kill的': sorted(set(victim_logics)),
            '说明': '能kill到≠0 → 这些逻辑共享同一个根本矛盾'}


def cmd_q3(store, args):
    sid = args['id']
    sur, err = get_or_fail(store, sid, 'surface')
    if err:
        return {'ok': False, 'msg': err}
    logics = _logics_of(store, sid)
    cur = logics
    n = len(cur)
    per = {}
    for L in cur:
        per[L['id']] = len(L.get('variants') or [])
    total = sum(per.values()) or 1
    warn = n == 1 or any(c == total for c in per.values()) or (n > 1 and max(per.values(), default=0) == total)
    # 独有变体数
    uniq = {}
    for L in cur:
        ids = set(L.get('variants') or [])
        other = set()
        for L2 in cur:
            if L2['id'] != L['id']:
                other |= set(L2.get('variants') or [])
        uniq[L['id']] = len(ids - other)
    return {'ok': True, 'msg': 'Q3：垄断度',
            '逻辑数': n, '独有变体数': uniq,
            '告警': bool(warn or (n == 1)),
            '说明': 'N=1 或某条独有变体数=总数 → 先到者垄断'}


def cmd_check(store, args):
    recs = store.records()
    errs = []
    cur = {}
    for r in recs:
        cur[r['id']] = r
    for rid, r in cur.items():
        k = r.get('kind')
        if k == 'logic':
            if r['state'] == STATE_HALF:
                errs.append(f'{rid}: 单栏是非法态（必须补进行时）')
            if r['state'] == STATE_TEST and not (r.get('variants') or []):
                errs.append(f'{rid}: 被测试但零变体（提出推翻但没产出）')
            if r['state'] == STATE_CLOSED:
                seams = [s for s in store.seams() if r['id'] in s.get('targets', []) and s.get('op') == 'close']
                if not seams or not seams[-1].get('reason'):
                    errs.append(f'{rid}: 封闭但没写 reason')
            if r.get('done') and not r.get('doing') and r['state'] != STATE_EMPTY:
                errs.append(f'{rid}: 有完成时没进行时')
    # 缝 op 合法性
    for s in store.seams():
        if s.get('op') not in LEGAL_OPS:
            errs.append(f'缝 {s["id"]}: 非法 op {s.get("op")}（不许自定义）')
    return {'ok': not errs, 'msg': f'检查 {len(cur)} 条记录、{len(store.seams())} 条缝，{len(errs)} 个问题',
            '问题': errs}


def cmd_show(store, args):
    r = store.by_id(args['id'])
    if not r:
        return {'ok': False, 'msg': '找不到'}
    return {'ok': True, 'record': r}


def cmd_seams(store, args):
    n = int(args.get('tail', 10))
    ss = store.seams()[-n:]
    return {'ok': True, 'seams': ss}


def parse(argv):
    cmd = argv[0] if argv else 'help'
    args = {}
    rest = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a.startswith('--'):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                args[key] = argv[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            rest.append(a)
            i += 1
    if rest:
        args['id'] = rest[0]
    return cmd, args


CMDS = {
    'init': cmd_init, 'surface': cmd_surface, 'logic': cmd_logic,
    'done': cmd_done, 'doing': cmd_doing, 'challenge': cmd_challenge,
    'variant': cmd_variant, 'close': cmd_close, 'reopen': cmd_reopen,
    'merge-same': cmd_merge_same,
    'q1': cmd_q1, 'q2': cmd_q2, 'q3': cmd_q3,
    'check': cmd_check, 'show': cmd_show, 'seams': cmd_seams,
}


def main():
    # Windows 终端默认 GBK，中文会乱码；强制 UTF-8 输出
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
    if cmd != 'init':
        if not os.path.exists(store.records_path):
            store.init()
    res = CMDS[cmd](store, args)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
