"""TTL 缓存的命中、失效、用户隔离测试。"""
from cache import make_key, get, set as cache_set, get_or_compute, invalidate_user, clear_all


def setup_function(_):
    clear_all()


def test_set_and_get():
    cache_set("k1", {"a": 1})
    assert get("k1") == {"a": 1}


def test_get_or_compute_caches_result():
    calls = []

    def compute():
        calls.append(1)
        return 42

    assert get_or_compute("k", compute) == 42
    assert get_or_compute("k", compute) == 42
    assert len(calls) == 1, "第二次应命中缓存而不再调用 compute"


def test_invalidate_user_clears_only_that_user():
    cache_set(make_key(1, "monthly"), [{"m": "2025-01"}])
    cache_set(make_key(2, "monthly"), [{"m": "2025-01"}])
    invalidate_user(1)
    assert get(make_key(1, "monthly")) is None
    assert get(make_key(2, "monthly")) is not None


def test_make_key_stable_across_param_order():
    a = make_key(1, "ns", year="2025", month="2025-01")
    b = make_key(1, "ns", month="2025-01", year="2025")
    assert a == b
