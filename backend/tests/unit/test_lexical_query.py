from time import perf_counter

import pytest

from app.retrieval.lexical_query import parse_lexical_terms


def test_extracts_terms_from_natural_language_and_removes_stopwords() -> None:
    assert parse_lexical_terms("Where is the alert controller?") == (
        "alert",
        "controller",
    )


def test_preserves_api_path_before_adding_its_components() -> None:
    assert parse_lexical_terms("Which method handles /api/users/{userId}?") == (
        "/api/users/{userid}",
        "api",
        "users",
        "userid",
        "user",
        "id",
        "method",
        "handles",
    )


def test_preserves_dotted_camel_case_identifier_and_adds_components() -> None:
    assert parse_lexical_terms("SysUserController.getUserProfile") == (
        "sysusercontroller.getuserprofile",
        "sysusercontroller",
        "sys",
        "user",
        "controller",
        "getuserprofile",
        "get",
        "profile",
    )


def test_preserves_snake_case_identifier_and_adds_components() -> None:
    assert parse_lexical_terms("find user_profile by account_id") == (
        "find",
        "user_profile",
        "user",
        "profile",
        "by",
        "account_id",
        "account",
        "id",
    )


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("_private_method", ("_private_method", "private", "method")),
        ("__init__", ("__init__", "init")),
        ("foo._bar", ("foo._bar", "foo", "_bar", "bar")),
    ],
)
def test_preserves_leading_underscore_identifiers_and_adds_components(
    identifier: str,
    expected: tuple[str, ...],
) -> None:
    assert parse_lexical_terms(identifier) == expected


def test_casefolds_and_deduplicates_terms_in_first_seen_order() -> None:
    assert parse_lexical_terms("User user USER Controller user") == (
        "user",
        "controller",
    )


@pytest.mark.parametrize("query", ["", "   ", "the is where and for to of in at a an"])
def test_empty_or_stopword_only_query_returns_no_terms(query: str) -> None:
    assert parse_lexical_terms(query) == ()


def test_preserves_cjk_chunks_and_casefolds_other_unicode_words() -> None:
    assert parse_lexical_terms("用户资料 Café CAFÉ naïve") == (
        "用户资料",
        "café",
        "naïve",
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("$emit", ("$emit", "emit")),
        (
            "this.$router.push",
            ("this.$router.push", "this", "$router", "router", "push"),
        ),
        ("Outer$Inner", ("outer$inner", "outer", "inner")),
        ("cafe\u0301", ("café",)),
        (
            "user-profile.vue",
            ("user-profile.vue", "user-profile", "user", "profile", "vue"),
        ),
    ],
)
def test_preserves_code_punctuation_and_normalizes_unicode(
    query: str,
    expected: tuple[str, ...],
) -> None:
    assert parse_lexical_terms(query) == expected


def test_stops_as_soon_as_max_terms_is_reached() -> None:
    assert parse_lexical_terms("one two three four", max_terms=2) == ("one", "two")


def test_default_bound_counts_plain_alphanumeric_words_as_single_terms() -> None:
    query = " ".join(f"term{index}" for index in range(20))

    assert parse_lexical_terms(query, max_terms=12) == tuple(
        f"term{index}" for index in range(12)
    )


def test_rejects_non_positive_max_terms() -> None:
    with pytest.raises(ValueError, match="max_terms"):
        parse_lexical_terms("anything", max_terms=0)


@pytest.mark.parametrize("symbol", ["%", "_", "$"])
def test_preserves_safe_standalone_symbol_query(symbol: str) -> None:
    assert parse_lexical_terms(symbol) == (symbol,)


@pytest.mark.parametrize(
    "identifier",
    [
        "a\u0338",
        "क्",
    ],
)
def test_preserves_unicode_identifier_combining_marks(identifier: str) -> None:
    assert parse_lexical_terms(identifier) == (identifier,)


def test_long_queries_scale_without_scanning_every_path_for_every_word() -> None:
    def duration(term_count: int) -> float:
        query = ("/a " * term_count) + ("the " * term_count)
        started = perf_counter()
        parse_lexical_terms(query)
        return perf_counter() - started

    small = min(duration(500) for _ in range(2))
    large = min(duration(4_000) for _ in range(2))

    assert large < 2.5
    assert large <= max(small * 20, 0.05)
