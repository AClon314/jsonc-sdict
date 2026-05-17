"""Public package exports for jsonc_sdict.

Core usage:
```python
from functools import partial
from jsonc_sdict import jsoncDict, CommentIn, NONE, sdict, get1, merge

jc = jsoncDict({CommentIn(NONE, "a"): "// before a", "a": 1, "b": 2})
jc[CommentIn("a", "b")] = "// between a and b"
print(jc.full)

data = sdict({"a": {"b": [0, {"c": 1}]}})
print(data["a", "b", 1, "c"])

old = {"items": [{"id": 1, "name": "old"}]}
new = {"items": [{"id": 1, "name": "new"}]}
merged = merge(
    (old, new),
    dictDict={"value_of_idKey": partial(get1.item, keys="id")},
    unMergeable="new",
)()
print(merged)
```

JSONC text input is also supported:
```python
import hjson
from jsonc_sdict import jsoncDict

jc = jsoncDict('{"a": 1}', loads=hjson.loads, dumps=hjson.dumps)
jc["a"] = 2
print(jc.full)
```
"""

from .share import NONE, UNSET
from .jsonc import (
    json_dumps,
    is_comment,
    CommentIn,
    jsoncDict,
    hjsonDict,
    CompactJSONEncoder,
)
from .GetSetDel import gets, get1, set1
from .Sdict import sdict, dfs
from .Merge import merge
