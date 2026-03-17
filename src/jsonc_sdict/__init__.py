"""Usage:
```python

```
"""

from .jsonc import jsoncDict, hjsonDict, CompactJSONEncoder
from .sdict import (
    sdict,
    unref,
    dfs,
    dictDict,
    get_children,
    get_item_attr,
    get_item,
    get_attr,
    set_item,
    set_item_attr,
    del_item,
    del_item_attr,
)
from .merge import merge
from .weakList import WeakList, OrderedWeakSet
from .share import (
    iterable,
    return_of,
    yields_of,
    in_range,
    copy_args,
    len_slice,
    NONE,
)
