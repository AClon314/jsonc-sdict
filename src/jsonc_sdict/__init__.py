"""Public package exports for jsonc_sdict.

Quick usage:
```python
import hjson
from jsonc_sdict import jsoncDict, CommentIn, NONE

jc = jsoncDict('{"a": 1}', loads=hjson.loads, dumps=hjson.dumps)
jc["a"] = 2
jc[CommentIn(NONE, "a")] = "// before a"
print(jc.full)
```

Advanced usage:
```python
jc[CommentIn("a")] = {
    CommentIn("k", ":"): "/* key slot */",
    CommentIn(":", "v"): "/* value slot */",
    CommentIn("v", ","): "/* tail slot */",
}
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
