from decimal import Decimal as D
from app.settings import TRACK_MAIN

QUANTUM = D('0.001')
GAP = '空档'


def _boundaries(segments):
    points = set()
    for seg in segments:
        points.add(seg['start'])
        points.add(seg['end'])
    return sorted(points)


def _active(segments, left, right):
    return [seg for seg in segments if seg['start'] <= left and right <= seg['end']]


def _rank(seg):
    # 同一切片同轨多段时的确定性次序：主轨优先，再按起点、来源行、键。
    return (0 if seg['track'] == TRACK_MAIN else 1, seg['start'], seg['line'], seg['key'])


def plan(segments):
    """扫分校准时间轴并用动态规划求最优交接序列。

    每个基础切片只留一路；空档（两路皆无）单独标出并断开前后，不产生换声。
    优化目标按字典序：换声次数最少 → 主轨实际取用时长最多 → 主轨优先的确定性次序。
    """
    if not segments:
        empty = {'switches': 0, 'covered': D('0.000'), 'gap': D('0.000'),
                 'span_start': None, 'span_end': None}
        return [], [], empty
    cuts = _boundaries(segments)
    slices = []
    for left, right in zip(cuts, cuts[1:]):
        width = (right - left).quantize(QUANTUM)
        if width <= 0:
            continue
        active = _active(segments, left, right)
        slices.append((left, right, width, active))

    # dp[key] = (换声数, -主轨毫秒, 次序罚分)，parent 记录上一切片选中键。
    dp, parents = [], []
    prev_dp = {}
    for index, (left, right, width, active) in enumerate(slices):
        if not active:
            dp.append(None)
            parents.append(None)
            prev_dp = {}
            continue
        cur_dp, cur_parent = {}, {}
        for seg in sorted(active, key=_rank):
            penalty = _rank(seg)
            is_main = seg['track'] == TRACK_MAIN
            if not prev_dp:
                candidate = (0, D('0'), penalty)
                cur_parent[seg['key']] = None
            else:
                best_key, best_val = None, None
                for prior_key, prior in prev_dp.items():
                    prior_track = prior[3]
                    change = 0 if prior_track == seg['track'] else 1
                    val = (prior[0] + change, prior[1], prior[2])
                    if best_val is None or val < best_val:
                        best_val, best_key = val, prior_key
                candidate = best_val
                cur_parent[seg['key']] = best_key
            switches, neg_main, penalty = candidate
            cur_dp[seg['key']] = (switches,
                                  neg_main - (width if is_main else D('0')),
                                  penalty, seg['track'])
        dp.append(cur_dp)
        parents.append(cur_parent)
        prev_dp = cur_dp

    # 终态择优并回溯。
    last_cover = max(i for i, state in enumerate(dp) if state is not None)
    terminal = min(dp[last_cover], key=lambda k: (dp[last_cover][k][0],
                                                  dp[last_cover][k][1],
                                                  dp[last_cover][k][2]))
    chosen_keys = [None] * len(slices)
    cursor = terminal
    for index in range(last_cover, -1, -1):
        if dp[index] is None:
            # 空档：前后断开，下一个覆盖切片从自身重新起点。
            cursor = None
            continue
        if cursor is None:
            # 空档之后的首个覆盖切片，parent 为 None，取该切片最优候选。
            cursor = min(dp[index], key=lambda k: (dp[index][k][0], dp[index][k][1], dp[index][k][2]))
        chosen_keys[index] = cursor
        cursor = parents[index][cursor]

    sequence = []
    key_to_seg = {seg['key']: seg for seg in segments}
    for index, (left, right, width, active) in enumerate(slices):
        if not active:
            sequence.append({'kind': GAP, 'track': None, 'key': None, 'line': None,
                             'start': left, 'end': right, 'duration': width, 'overlap': False})
            continue
        chosen = key_to_seg[chosen_keys[index]]
        sequence.append({'kind': '取用', 'track': chosen['track'], 'key': chosen['key'],
                         'line': chosen['line'], 'start': left, 'end': right, 'duration': width,
                         'overlap': len(active) > 1})
    gaps = [dict(item) for item in sequence if item['kind'] == GAP]
    items = _coalesce(sequence)
    switches = sum(1 for a, b in zip(items, items[1:])
                   if a['kind'] == '取用' and b['kind'] == '取用' and a['track'] != b['track'])
    covered = sum((i['duration'] for i in items if i['kind'] == '取用'), D('0'))
    gap_total = sum((g['duration'] for g in gaps), D('0'))
    stats = {'switches': switches, 'covered': covered.quantize(QUANTUM),
             'gap': gap_total.quantize(QUANTUM), 'span_start': cuts[0], 'span_end': cuts[-1]}
    return items, gaps, stats


def _coalesce(sequence):
    """合并相邻、同来源（同片段同轨）的切片；空档保持独立且保留时间顺序。"""
    items = []
    for sl in sequence:
        if sl['kind'] == GAP:
            items.append(dict(sl))
            continue
        if items and items[-1]['kind'] == '取用' and items[-1]['key'] == sl['key'] \
                and items[-1]['track'] == sl['track'] and items[-1]['end'] == sl['start']:
            last = items[-1]
            last['end'] = sl['end']
            last['duration'] = (last['duration'] + sl['duration']).quantize(QUANTUM)
            last['overlap'] = last['overlap'] or sl['overlap']
        else:
            items.append(dict(sl))
    return items


def usage(items):
    """按片段汇总实际取用时长（毫秒），仅统计真正接入交接的部分。"""
    ledger = {}
    for item in items:
        if item['kind'] != '取用':
            continue
        identity = (item['key'], item['track'])
        ledger[identity] = ledger.get(identity, D('0')) + item['duration']
    return {key: value.quantize(QUANTUM) for key, value in sorted(ledger.items())}
