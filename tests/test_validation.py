import pytest

from rossum_user_loader import core
from rossum_user_loader import validation as v


def test_allowed_row_keys_in_sync_with_core():
    # Drift guard: every loader column must be accepted; the only extra is 'action'.
    assert set(core.SUPPORTED_COLUMNS.keys()) <= set(v.ALLOWED_ROW_KEYS)
    assert "action" in v.ALLOWED_ROW_KEYS


@pytest.mark.parametrize("bad", ["", "   ", "a b", "tok\nen", "x" * (v.MAX_TOKEN_LEN + 1)])
def test_validate_token_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_token(bad)


def test_validate_token_ok():
    assert v.validate_token("  abc123  ") == "abc123"


@pytest.mark.parametrize(
    "bad", ["", "ftp://x", "not a url", "javascript:alert(1)", "x" * (v.MAX_URL_LEN + 1)]
)
def test_validate_domain_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_domain(bad)


def test_validate_domain_ok_strips_trailing_slash():
    assert v.validate_domain("https://x.rossum.app/api/v1/") == "https://x.rossum.app/api/v1"


@pytest.mark.parametrize("bad", ["", "abc", "12a", "-5", "0", str(v.MAX_ORG_ID + 1), "1;DROP TABLE"])
def test_validate_org_id_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_org_id(bad)


def test_validate_org_id_ok():
    assert v.validate_org_id(" 42 ") == "42"


def test_validate_org_id_rejects_unicode_digits():
    # Arabic-Indic digits are str.isdigit()==True but must NOT be accepted.
    with pytest.raises(v.ValidationError):
        v.validate_org_id("٥٣")


def test_validate_rows_drops_unknown_keys_and_keeps_newline():
    out = v.validate_rows([{"email": "a@x.io", "evil": "x", "queue_ids": "1\n2"}])
    assert out == [{"email": "a@x.io", "queue_ids": "1\n2"}]


def test_validate_rows_strips_dangerous_control_chars():
    out = v.validate_rows([{"first_name": "Jo\x00hn\x07"}])
    assert out[0]["first_name"] == "John"


def test_validate_rows_rejects_too_many():
    with pytest.raises(v.ValidationError):
        v.validate_rows([{} for _ in range(v.MAX_ROWS + 1)])


def test_validate_rows_rejects_non_list():
    with pytest.raises(v.ValidationError):
        v.validate_rows({"not": "a list"})


def test_validate_rows_rejects_oversized_field():
    with pytest.raises(v.ValidationError):
        v.validate_rows([{"email": "x" * (v.MAX_FIELD_LEN + 1)}])


def test_validate_rows_rejects_non_dict_row():
    with pytest.raises(v.ValidationError):
        v.validate_rows(["notadict"])


@pytest.mark.parametrize("bad", ["", "   ", "a b", "u\nser", "x" * (v.MAX_USERNAME_LEN + 1)])
def test_validate_username_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_username(bad)


def test_validate_username_ok():
    assert v.validate_username("  jane@corp.com ") == "jane@corp.com"


@pytest.mark.parametrize("bad", ["", "pw\nwith-newline", "x" * (v.MAX_PASSWORD_LEN + 1)])
def test_validate_password_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_password(bad)


def test_validate_password_allows_spaces_and_symbols_unstripped():
    # Passwords are not stripped and may contain spaces/symbols.
    assert v.validate_password("  s p a c e $#@! ") == "  s p a c e $#@! "
