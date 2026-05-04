"""Public package exports for jsonc_sdict.

Quick usage:
```python
import hjson
from jsonc_sdict import jsoncDict, Within, NONE

jc = jsoncDict('{"a": 1}', loads=hjson.loads, dumps=hjson.dumps)
jc["a"] = 2
jc[Within(NONE, "a")] = "// before a"
print(jc.full)
```

Advanced usage:
```python
jc[Within("a")] = {
    Within("k", ":"): "/* key slot */",
    Within(":", "v"): "/* value slot */",
    Within("v", ","): "/* tail slot */",
}
print(jc.full)
```
"""

from .share import NONE, UNSET, _PKG_
from .jsonc import (
    json_dumps,
    is_comment,
    Within,
    jsoncDict,
    hjsonDict,
    CompactJSONEncoder,
)
from .Sdict import sdict, dfs
from .Merge import merge
