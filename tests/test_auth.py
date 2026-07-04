from src.auth.security import generate_api_key, hash_api_key, key_prefix


def test_generate_api_key_format():
    raw = generate_api_key()
    assert raw.startswith("ork_")


def test_hash_is_deterministic_with_pepper():
    a = hash_api_key("ork_test", "pepper")
    b = hash_api_key("ork_test", "pepper")
    c = hash_api_key("ork_test", "other")
    assert a == b
    assert a != c


def test_key_prefix():
    assert key_prefix("ork_abcdefghijklmnop") == "ork_abcdefgh"