"""tests/test_retcon.py — 零依赖断言：切段 / 双向流转 / 越界拒绝。

跑法：python tests/test_retcon.py（退出码 0 = 全过）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import retcon


def test_split():
    segs = retcon.split_segments('第一句。第二句！第三句？')
    assert segs == ['第一句', '第二句', '第三句'], segs


def test_flow():
    root = tempfile.mkdtemp(prefix='retcon-test-')
    s = retcon.Store(root)
    s.init()
    r1 = retcon.cmd_say(s, {'raw': '第一句话。第二句话。第三句话。'})
    assert r1['ok'] and len(r1['record']['segments']) == 3
    r2 = retcon.cmd_cover(s, {'id': 'T1', 'reads': '2'})
    assert r2['ok'] and r2['record']['reads'] == [2]
    worn, uses = retcon.wear_of(s, s.text('T1'))
    assert [w['i'] for w in worn] == [1, 3]
    r3 = retcon.cmd_study(s, {'id': 'T1', 'seg': '1', 'finding': 'ok'})
    assert r3['ok']
    r4 = retcon.cmd_trace(s, {'id': 'T1', 'segs': '1,2'})
    assert r4['ok']


def test_guard():
    root = tempfile.mkdtemp(prefix='retcon-guard-')
    s = retcon.Store(root)
    s.init()
    assert not retcon.cmd_cover(s, {'id': None, 'reads': '1'})['ok']
    assert not retcon.cmd_cover(s, {'id': 'T1', 'reads': '1'})['ok']
    retcon.cmd_say(s, {'raw': '第一句话。第二句话。'})
    assert not retcon.cmd_cover(s, {'id': 'T1', 'reads': '9'})['ok']
    assert not retcon.cmd_cover(s, {'id': 'T1', 'reads': ''})['ok']


if __name__ == '__main__':
    for name in ('test_split', 'test_flow', 'test_guard'):
        globals()[name]()
        print(f'ok {name}')
    print('ALL OK')
