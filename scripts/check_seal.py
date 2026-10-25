#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
封存检查器 · 按「五项标准」给一条记忆打分

用法：
  python scripts/check_seal.py 封存/20261025_xxx.md
  python scripts/check_seal.py 封存/            # 整个目录全查
  python scripts/check_seal.py 封存/ --quiet    # 只输出分数

标准（见 读取/标准.md）：
  1 假设位    2 证据指针    3 反例位    4 推翻条件    5 回访位

⚠ 第 4 项单独一票否决：缺「怎么推翻我」，总分直接归 0。
⚠ 它只判格式合格，不判内容对错 —— 内容对不对，需要另一套东西。
"""
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 第三节「后来」如果还是这句，说明没回访
NOT_YET = '还没结案'

# 废话反例：写了等于没写
EMPTY_EXCUSES = [
    '仅供参考', '不一定对', '可能不够全面', '可能不准确', '有待验证',
    '难免有误', '个人观点', '不喜勿喷',
]

# 假推翻：不可执行
FAKE_REFUTE = [
    '多想想', '再观察', '实践检验', '以后再说', '时间会证明', '看情况',
    '继续关注', '有待进一步', '后续验证',
]

# 「假设」的认领词
CLAIM_WORDS = ['我以为', '我猜', '我判断', '我假设', '初步', '可能', '推测', '怀疑', '估计']

# 证据里不算数的
NON_EVIDENCE = ['凭经验', '凭感觉', '大家都', '反正是', '众所周知']


def grab(text, *heads):
    """抓某个标题下的正文。支持多个候选标题。

    ⚠ 两条都是被抓出来的 bug，别再改回去：
      1. 标题允许带序号前缀：「## 三、后来」「## 3. 后来」都要认。
         原来只认标题就叫「后来」，把已经填过的回访判成没填。
      2. 抓到「同级或更高级」标题为止，不是到「任何标题」为止。
         原来用正则 `(.*?)(?=^#{1,6})`，节下面第一个东西是子标题时，
         会只抓到那个换行符 → 判成空节。（样例一的「注释」就是这么被误判的）
    """
    num_pat = r'(?:[一二三四五六七八九十百]+|\d+)\s*[、.．)）]\s*'
    lines = text.splitlines()
    for h in heads:
        for i, line in enumerate(lines):
            m = re.match(r'^(#{1,6})\s*(?:' + num_pat + r')?' + re.escape(h), line)
            if not m:
                continue
            level = len(m.group(1))
            out = []
            for j in range(i + 1, len(lines)):
                m2 = re.match(r'^(#{1,6})\s', lines[j])
                if m2 and len(m2.group(1)) <= level:
                    break
                out.append(lines[j])
            return '\n'.join(out).strip()
    return None


def items(section):
    """把一节拆成条目（1. / - / 空行分隔都算）。"""
    if not section:
        return []
    rows = []
    for line in section.splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r'^(\d+[.、)]|[-*+])\s*', '', s)
        if s:
            rows.append(s)
    return rows


def check_one(path):
    txt = io.open(path, encoding='utf-8').read()
    name = os.path.basename(path)
    r = {'file': name, 'score': 0, 'fails': [], 'warns': []}

    # ── 1 假设位
    # ⚠ 认领词只查「那是什么」一节不够：真实封存常把认领写在文件头部
    #   （「⚠ 我只看了 4 帧，这是假设，不是结论」）。
    #   做法：先查小节正文，再查文件前 15 行。两处都没有才算没认领。
    claim = grab(txt, '那是什么', '我的假设', '假设', '一句话')
    if not claim:
        r['fails'].append('① 假设位：找不到「那是什么 / 我的假设」这一节')
    else:
        body = re.sub(r'\s+', '', claim)
        head = '\n'.join(txt.splitlines()[:15])
        if len(body) < 6:
            r['fails'].append('① 假设位：几乎没写内容')
        elif not (any(w in claim for w in CLAIM_WORDS) or any(w in head for w in CLAIM_WORDS + ['这是假设', '只是假设', '尚未验证', '没验证'])):
            r['fails'].append('① 假设位：没有「我以为/我猜/初步」这类认领，像是在陈述事实')
        else:
            r['score'] += 1

    # ── 2 证据指针
    ev = items(grab(txt, '凭什么这么假设', '凭什么', '证据'))
    if not ev:
        r['fails'].append('② 证据指针：一条都没有')
    elif all(any(w in e for w in NON_EVIDENCE) for e in ev):
        r['fails'].append('② 证据指针：全是「凭感觉/大家都这么说」，指不到任何具体地方')
    else:
        r['score'] += 1
        for e in ev:
            if any(w in e for w in NON_EVIDENCE):
                r['warns'].append('② 有一条证据是虚的：%s' % e[:30])

    # ── 3 反例位
    wrong = items(grab(txt, '我可能错在哪', '可能错在哪', '反例'))
    if not wrong:
        r['fails'].append('③ 反例位：没写自己可能错在哪')
    elif all(any(w in w2 for w in EMPTY_EXCUSES) for w2 in wrong) or \
            all(len(w2) < 10 for w2 in wrong):
        r['fails'].append('③ 反例位：写了但等于没写（「仅供参考」这类）')
    else:
        r['score'] += 1

    # ── 4 推翻条件（一票否决）
    ref = grab(txt, '怎么推翻我', '推翻条件')
    ok4 = False
    if not ref:
        r['fails'].append('④ 推翻条件：没有这一节 —— 一票否决')
    else:
        body = re.sub(r'\s+', '', ref)
        if len(body) < 8:
            r['fails'].append('④ 推翻条件：太短，不像能执行的步骤')
        elif all(any(w in ref for w in FAKE_REFUTE) for _ in [0]) and any(w in ref for w in FAKE_REFUTE):
            r['fails'].append('④ 推翻条件：只有「多想想/再观察」这种不可执行的话')
        else:
            ok4 = True
            r['score'] += 1
            if any(w in ref for w in FAKE_REFUTE):
                r['warns'].append('④ 里面混了不可执行的词，确认一下真能照着做')

    # ── 5 回访位
    later = grab(txt, '后来')
    if later is None:
        r['fails'].append('⑤ 回访位：没有「后来」这一节，不打算回访 = 不是记忆，是留言')
    elif NOT_YET in later:
        r['warns'].append('⑤ 回访位：还没结案（这不算不合格，但要有人回来填）')
        r['unsettled'] = True
        r['score'] += 1
    else:
        r['score'] += 1

    # ── 一票否决
    if not ok4:
        r['score'] = 0
        r['vetoed'] = True

    # ── 附加项（不计分）：注释里有没有「成长性」那一句
    # ⚠ 只查「有没有一句下次能用的动作」，不查写得好不好 —— 那样会变成考核
    note = grab(txt, '注释')
    if note:
        if '成长性' not in note and '下次' not in note:
            r['warns'].append('⑥ 成长性：没写那一句「下次遇到同类事先做什么」')
        elif len(re.sub(r'\s+', '', note)) < 20:
            r['warns'].append('⑥ 成长性：短了点，确认那句是真能照着做的动作，不是感想')
    elif later and NOT_YET not in later:
        # 已经回访过却没有注释节
        r['warns'].append('⑥ 成长性：回访过了但没写注释 —— 经过没留下，下次要从零重想')

    return r


def bar(score):
    return '★' * score + '☆' * (5 - score)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    target = sys.argv[1]
    quiet = '--quiet' in sys.argv
    paths = []
    if os.path.isdir(target):
        paths = [os.path.join(target, f) for f in sorted(os.listdir(target))
                 if f.endswith('.md') and not f.startswith('_')]
    elif os.path.exists(target):
        paths = [target]
    else:
        print('找不到：%s' % target)
        return 1

    if not paths:
        print('目录里没有 .md 封存文件：%s' % target)
        return 1

    total = 0
    bad = 0
    for p in paths:
        r = check_one(p)
        total += r['score']
        if r['score'] < 5:
            bad += 1
        if quiet:
            print('%s  %s' % (bar(r['score']), r['file']))
            continue

        print('=' * 60)
        print('%s  %s  %d/5' % (bar(r['score']), r['file'], r['score']))
        if r.get('vetoed'):
            print('  ⚠ 一票否决：缺或不成立的第 ④ 项 → 总分归 0')
        for f in r['fails']:
            print('  ❌ ' + f)
        for w in r['warns']:
            print('  ⚠ ' + w)
        if r['score'] == 5 and not r.get('unsettled'):
            print('  ✅ 五项齐全，已结案')
        elif r['score'] == 5:
            print('  ✅ 五项齐全，但还没结案（它现在只是猜想，不是知识）')

    print('')
    print('共 %d 条，平均 %.1f 分，%d 条不合格' % (len(paths), total / len(paths), bad))
    print('⇒ 它只判格式合格，不判内容对错。内容对不对，需要另一套东西。')
    return 0 if bad == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
