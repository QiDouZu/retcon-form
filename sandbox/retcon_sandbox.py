#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retcon 沙盘 —— 不写文档，跑给你看。

在临时库里建原文、记使用、算磨损、反推段号，验 17 个场景。
跑法（在格式包根目录下）：
    python sandbox/retcon_sandbox.py
退出码：0 全过，1 有失败。

极端环境 = 原文超长 / 覆盖极稀 / 规模大 / 输入脏。
每个场景都从零建临时库，互不污染。
"""

import os
import sys
import time
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import retcon  # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix='retcon_sandbox_')
results = []
_inited = set()


def new_store():
    """每个 case 一个独立库目录，互不污染。"""
    d = tempfile.mkdtemp(dir=TMPDIR)
    store = retcon.Store(d)
    store.init()
    return store


def run(store, cmd, **args):
    return retcon.CMDS[cmd](store, args)


def case(name):
    def deco(fn):
        try:
            fn()
            results.append((name, 'PASS', ''))
        except AssertionError as e:
            results.append((name, 'FAIL', str(e)[:300]))
        except Exception as e:  # 崩溃也算失败，不藏
            results.append((name, 'FAIL', f'{type(e).__name__}: {e}'[:300]))
        return fn
    return deco


def assert_eq(got, want, label=''):
    if got != want:
        raise AssertionError(f'{label}: 期望 {want!r}，实际 {got!r}')


def assert_true(cond, msg=''):
    if not cond:
        raise AssertionError(msg or '断言失败')


# ---------------------------------------------------------------- 场景组一：原文不可变

@case('1 原文永不被写：同一句说两次，第二次复用、原文不动')
def t1():
    s = new_store()
    run(s, 'init')
    a = run(s, 'say', raw='人类是穷的，因为她是富的。', source='原话')
    assert_true(a['ok'], '第一次 say 失败')
    b = run(s, 'say', raw='人类是穷的，因为她是富的。')
    assert_true(b.get('reuse'), '同一句没被识别为复用')
    assert_eq(len(s.all_texts()), 1, '原文条数')


@case('2 显式 id 冲突：同 id 不同文，拒绝，不覆盖')
def t2():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='第一版。', id='T1')
    r = run(s, 'say', raw='第二版。', id='T1')
    assert_true(not r['ok'], '同 id 冲突没被拒绝')
    assert_eq(s.text('T1')['raw'], '第一版。', '原文被覆盖')


# ---------------------------------------------------------------- 场景组二：磨损是算出来的

@case('3 没覆盖就没有磨损：说了一句从没用过')
def t3():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='没被用过的句子。')
    r = run(s, 'wear', id='T1')
    assert_true(r['ok'])
    assert_eq(r['磨损段'], [], '没用过却算出磨损')


@case('4 极端压缩：200 段只带走 1 段，磨损 199')
def t4():
    s = new_store()
    run(s, 'init')
    raw = '，'.join(['第%d段' % i for i in range(1, 201)]) + '。'
    run(s, 'say', raw=raw)
    r = run(s, 'cover', id='T1', reads='1', context='只看开头')
    assert_true(r['ok'], 'cover 失败')
    w = run(s, 'wear', id='T1')
    assert_eq(w['原文段数'], 200, '段数')
    assert_eq(w['磨损段数'], 199, '磨损段数')


@case('5 覆盖完整：全部段带走，磨损归零')
def t5():
    s = new_store()
    run(s, 'init')
    raw = '，'.join(['第%d段' % i for i in range(1, 11)]) + '。'
    run(s, 'say', raw=raw)
    run(s, 'cover', id='T1', reads='1,2,3,4,5,6,7,8,9,10')
    w = run(s, 'wear', id='T1')
    assert_eq(w['磨损段数'], 0, '全覆盖还能算出磨损')


# ---------------------------------------------------------------- 场景组三：输入脏也不炸

@case('6 乱序覆盖：3,1,2 被排序成 1,2,3')
def t6():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己，庚辛。')
    r = run(s, 'cover', id='T1', reads='3,1,2')
    assert_eq(r['record']['reads'], [1, 2, 3], 'reads 未排序')


@case('7 越界段号：999 拒绝，不污染库')
def t7():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁。')
    r = run(s, 'cover', id='T1', reads='999')
    assert_true(not r['ok'], '越界没被拒绝')
    assert_eq(len(s.all_uses()), 0, '越界记录被写进去了')


@case('8 空原文：拒绝，不建脏句子')
def t8():
    s = new_store()
    run(s, 'init')
    r = run(s, 'say', raw='   ')
    assert_true(not r['ok'], '空原文被接受')


@case('9 无标点长句：切成 1 段不崩')
def t9():
    s = new_store()
    run(s, 'init')
    r = run(s, 'say', raw='这是一句没有任何标点的超长原文' * 50)
    assert_eq(len(r['record']['segments']), 1, '段数')


@case('10 中英混排 + 重复段号：去重后覆盖并集正确')
def t10():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='hello world，第二段。第三段？')
    r = run(s, 'cover', id='T1', reads='2,2,2')
    assert_eq(r['record']['reads'], [2], '重复段号未去重')


# ---------------------------------------------------------------- 场景组四：强制单一变量

@case('11 study 不给段号：拒绝（一次只研究一段）')
def t11():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己。')
    r = run(s, 'study', id='T1', finding='整体上不对劲')
    assert_true(not r['ok'], '没给段号却接受了')


@case('12 study 不给发现：拒绝')
def t12():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己。')
    r = run(s, 'study', id='T1', seg=2)
    assert_true(not r['ok'], '没写发现却接受了')


@case('13 study 合法：记录落盘、磨损状态变「已研究」')
def t13():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己，庚辛。')
    run(s, 'cover', id='T1', reads='1')
    r = run(s, 'study', id='T1', seg=2, finding='第2段之前完全没带走', next='去看第2段原文')
    assert_true(r['ok'])
    v = run(s, 'vars', id='T1')
    states = {row['段']: row['状态'] for row in v['变量']}
    assert_eq(states[2], '已研究', '第2段状态')


# ---------------------------------------------------------------- 场景组五：结果可反推

@case('14 反推：一个段号能查回是第几次使用带来的')
def t14():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己，庚辛，壬癸。')
    run(s, 'cover', id='T1', reads='2,5', context='第一次读')
    r = run(s, 'trace', id='T1', segs='5')
    assert_true(r['ok'])
    assert_eq(len(r['由哪几次使用支撑']), 1, '支撑次数')
    assert_eq(r['由哪几次使用支撑'][0]['带走的段'], [5], '段号')


@case('15 反推多源：两次使用都带过同一段')
def t15():
    s = new_store()
    run(s, 'init')
    run(s, 'say', raw='甲乙，丙丁，戊己，庚辛。')
    run(s, 'cover', id='T1', reads='1')
    run(s, 'cover', id='T1', reads='1,2')
    r = run(s, 'trace', id='T1', segs='1')
    assert_eq(len(r['由哪几次使用支撑']), 2, '支撑来源数')


# ---------------------------------------------------------------- 场景组六：极端环境

@case('16 规模：300 句 × 每句 5 次使用，check 全绿、磨损可算、耗时可控')
def t16():
    s = new_store()
    run(s, 'init')
    t0 = time.perf_counter()
    for k in range(1, 301):
        run(s, 'say', raw='，'.join(['第%d句的%d段' % (k, i) for i in range(1, 21)]) + '。')
    for k in range(1, 301):
        tid = 'T%d' % k
        for u in range(5):
            run(s, 'cover', id=tid, reads='%d,%d,%d' % (u + 1, u + 2, u + 3),
                context='第%d次使用' % u)
    c = run(s, 'check')
    assert_true(c['ok'], 'check 报错：%s' % c.get('问题'))
    w = run(s, 'wear', id='T150')
    assert_eq(w['磨损段数'], 13, 'T150 磨损段数')  # 20 段，覆盖 1..7 共 7 段，剩 13
    dt = time.perf_counter() - t0
    assert_true(dt < 60, '太慢：%.1fs' % dt)
    results.append(('   · 300 句 + 1500 次使用耗时', 'INFO', '%.2fs' % dt))


@case('17 极端环境·AI 只有压缩结论：50 句里靠磨损定位缺口')
def t17():
    s = new_store()
    run(s, 'init')
    for k in range(1, 51):
        run(s, 'say', raw='，'.join(['原文%d-%d' % (k, i) for i in range(1, 9)]) + '。')
    # 一个"只会读压缩结论"的 AI：每句只带走第 1 段
    for k in range(1, 51):
        run(s, 'cover', id='T%d' % k, reads='1', context='只看了结论')
    # 它现在只有"结论"，不知道被压掉了什么 → 磨损清单告诉它
    w = run(s, 'wear', id='T25')
    assert_eq(w['磨损段数'], 7, 'T25 被压掉的段数')
    # 顺着磨损去反推原文，能定位到段
    r = run(s, 'trace', id='T25', segs='5')
    assert_eq(r['反推目标段'][0]['text'], '原文25-5', '反推出的原文')


# ---------------------------------------------------------------- 收尾

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print('retcon 沙盘 · 17 个场景（临时库：%s）\n' % TMPDIR)
    fails = 0
    for name, status, detail in results:
        mark = {'PASS': 'PASS', 'FAIL': 'FAIL', 'INFO': 'INFO '}[status]
        print(f'[{mark}] {name}')
        if status == 'FAIL':
            print(f'        {detail}')
            fails += 1
    print('\n—— %d 个场景，%d 失败 ——' % (len(results) - 1, fails))
    shutil.rmtree(TMPDIR, ignore_errors=True)
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
