"""Usage:
```python
from jsonc_sdict import jsoncDict, sdict, merge, WeakList, NONE
```
"""

from .share import NONE, UNSET, _PKG_
from .jsonc import jsoncDict, hjsonDict, CompactJSONEncoder
from .Sdict import sdict, dfs
from .Merge import merge
