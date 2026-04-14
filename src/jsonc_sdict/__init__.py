"""Usage:
```python
from jsonc_sdict import jsoncDict, sdict, merge, WeakList, NONE
```
"""

from .share import NONE, _PKG_
from .jsonc import jsoncDict, hjsonDict, CompactJSONEncoder
from .sdict import sdict as Sdict, dfs
from .merge import merge as Merge
from .weakList import WeakList
