import timeit
from jsonc_sdict.weakList import Ref, WeakList, OrderedWeakSet


def benchmark():
    N = 1000
    refs = [Ref(i) for i in range(N)]

    print(f"Performance Benchmark (N={N})")
    print("-" * 40)

    # 1. Addition / Insertion
    def test_add_weaklist():
        wl = WeakList()
        for r in refs:
            wl.append(r)

    def test_add_orderedweakset():
        ows = OrderedWeakSet()
        for r in refs:
            ows.add(r)

    t_add_wl = timeit.timeit(test_add_weaklist, number=100)
    t_add_ows = timeit.timeit(test_add_orderedweakset, number=100)
    print("Add/Append (100 runs):")
    print(f"  WeakList:       {t_add_wl:.4f}s")
    print(f"  OrderedWeakSet: {t_add_ows:.4f}s")

    # 2. Iteration
    wl = WeakList(refs)
    ows = OrderedWeakSet(refs)

    def test_iter_weaklist():
        for _ in wl:
            pass

    def test_iter_orderedweakset():
        for _ in ows:
            pass

    t_iter_wl = timeit.timeit(test_iter_weaklist, number=1000)
    t_iter_ows = timeit.timeit(test_iter_orderedweakset, number=1000)
    print("\nIteration (1000 runs):")
    print(f"  WeakList:       {t_iter_wl:.4f}s")
    print(f"  OrderedWeakSet: {t_iter_ows:.4f}s")

    # 3. Containment Check
    wl_no_repeat = WeakList(refs, noRepeat=True)

    def test_contains_weaklist_norepeat():
        for r in refs:
            _ = r in wl_no_repeat

    def test_contains_weaklist():
        for r in refs:
            _ = r in wl

    def test_contains_orderedweakset():
        for r in refs:
            _ = r in ows

    t_contains_wl_nr = timeit.timeit(test_contains_weaklist_norepeat, number=100)
    t_contains_wl = timeit.timeit(test_contains_weaklist, number=100)
    t_contains_ows = timeit.timeit(test_contains_orderedweakset, number=100)
    print("\nContainment Check (100 runs):")
    print(f"  WeakList (noRepeat=False): {t_contains_wl:.4f}s")
    print(f"  WeakList (noRepeat=True):  {t_contains_wl_nr:.4f}s")
    print(f"  OrderedWeakSet:            {t_contains_ows:.4f}s")

    # 4. Remove / Discard
    def test_remove_weaklist():
        wl_temp = WeakList(refs)
        for r in refs:
            wl_temp.remove(r)

    def test_remove_orderedweakset():
        ows_temp = OrderedWeakSet(refs)
        for r in refs:
            ows_temp.discard(r)

    t_remove_wl = timeit.timeit(test_remove_weaklist, number=10)
    t_remove_ows = timeit.timeit(test_remove_orderedweakset, number=10)
    print("\nRemove/Discard (10 runs):")
    print(f"  WeakList:       {t_remove_wl:.4f}s")
    print(f"  OrderedWeakSet: {t_remove_ows:.4f}s")


if __name__ == "__main__":
    benchmark()
