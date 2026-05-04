"""Match similar lines between two ordered string sequences.

This module treats highly similar `old`/`new` line pairs as modifications and
keeps the remaining unmatched lines as deletions or insertions.

# TODO: 改变diff算法，改用 fast_diff_match_patch

对于合并带\n的多行文本str，有如下例子

## old
```
add
modify，整体
modify，零碎
remove
```
## new
```
前面加点，add, 后面加点
整体修改，modify
零mod碎ify修改
```
## merged
```
前面加点，add, 后面加点
整体修改，modify，整体
(用户手动处理 or 同时保留old与new为2行)
remove
```
其中如果同时保留，则根据前后缀配置`keep_with={"old", ("<old>", "</old>\n"), "new": ("<new>", "</new>\n")}`，效果如下
```
前面加点，add, 后面加点
整体修改，modify，整体
<old>modify，零碎</old>
<new>零mod碎ify修改</new>
remove
```

# 引入零碎评分
TODO: 评分算法？
低于该阈值，则为零碎修改，进入选择：
- 若用户覆盖了默认前后缀配置为None，则类似Merge一样，for循环里抛出来让用户手动处理
- 否则，添加为2行，带前后缀

"""

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

import fast_diff_match_patch as dmp


@dataclass
class SimilarLineMatchResult:
    """Structured result returned by :func:`match_similar_lines`."""

    matches: dict[tuple[int, int], tuple[str, str]]
    """Matched `(old_index, new_index) -> (old_line, new_line)` pairs."""
    old_only: list[tuple[int, str]]
    """Unmatched old lines as `(old_index, old_line)` tuples."""
    new_only: list[tuple[int, str]]
    """Unmatched new lines as `(new_index, new_line)` tuples."""


def _is_crossing(old_i: int, new_j: int, accepted: Sequence[tuple[int, int]]) -> bool:
    """Return whether a candidate pair would break the current index order."""

    for accepted_old_i, accepted_new_j in accepted:
        if (old_i - accepted_old_i) * (new_j - accepted_new_j) < 0:
            return True
    return False


def _match_replace_block(
    old: Sequence[str],
    new: Sequence[str],
    old_start: int,
    old_stop: int,
    new_start: int,
    new_stop: int,
    threshold: float,
) -> SimilarLineMatchResult:
    """Match one `replace` block while preserving one-to-one, non-crossing pairs.

    Candidate pairs are scored with ``SequenceMatcher.ratio()`` and filtered by
    ``threshold``. The remaining pairs are greedily selected in descending score
    order while keeping indices monotonic.
    """

    candidates: list[tuple[float, int, int, int]] = []
    for old_i in range(old_start, old_stop):
        old_line = old[old_i]
        local_old_i = old_i - old_start
        for new_j in range(new_start, new_stop):
            new_line = new[new_j]
            score = SequenceMatcher(None, old_line, new_line, autojunk=False).ratio()
            if score >= threshold:
                local_new_j = new_j - new_start
                candidates.append((score, abs(local_old_i - local_new_j), old_i, new_j))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))

    accepted_pairs: list[tuple[int, int]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()
    matches: dict[tuple[int, int], tuple[str, str]] = {}

    for _, _, old_i, new_j in candidates:
        if old_i in used_old or new_j in used_new:
            continue
        if _is_crossing(old_i, new_j, accepted_pairs):
            continue
        accepted_pairs.append((old_i, new_j))
        used_old.add(old_i)
        used_new.add(new_j)
        matches[(old_i, new_j)] = (old[old_i], new[new_j])

    old_only = [
        (old_i, old[old_i])
        for old_i in range(old_start, old_stop)
        if old_i not in used_old
    ]
    new_only = [
        (new_j, new[new_j])
        for new_j in range(new_start, new_stop)
        if new_j not in used_new
    ]
    return SimilarLineMatchResult(matches=matches, old_only=old_only, new_only=new_only)


def match_similar_lines(
    old: Sequence[str],
    new: Sequence[str],
    threshold: float = 0.6,
) -> SimilarLineMatchResult:
    """Match similar lines between `old` and `new`.

    The algorithm first uses line-level ``SequenceMatcher.get_opcodes()`` to
    split the inputs into ``equal``/``delete``/``insert``/``replace`` blocks.
    Only ``replace`` blocks are further inspected for similar line pairs.

    Args:
        old: Original lines in their original order.
        new: Updated lines in their updated order.
        threshold: Minimum similarity ratio required to treat two lines as a
            modification pair.

    Returns:
        A :class:`SimilarLineMatchResult` containing matched modified lines and
        the unmatched old/new lines.
    """

    matches: dict[tuple[int, int], tuple[str, str]] = {}
    old_only: list[tuple[int, str]] = []
    new_only: list[tuple[int, str]] = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(
        a=old, b=new, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            old_only.extend((old_i, old[old_i]) for old_i in range(i1, i2))
            continue
        if tag == "insert":
            new_only.extend((new_j, new[new_j]) for new_j in range(j1, j2))
            continue

        block_result = _match_replace_block(old, new, i1, i2, j1, j2, threshold)
        matches.update(block_result.matches)
        old_only.extend(block_result.old_only)
        new_only.extend(block_result.new_only)

    return SimilarLineMatchResult(
        matches=matches,
        old_only=old_only,
        new_only=new_only,
    )
