import pytest
from new_logger.sanitization.url_sanitizer import sanitize_url


@pytest.mark.unit
def test_sanitize_url_drops_fragment_userinfo_and_redacts_sensitive_key():
    result = sanitize_url(
        "https://user:pass@Example.COM:8080/a/123?token=abc&lang=en#frag"
    )

    assert result.sanitized_url == (
        "https://example.com:8080/a/[INT]?lang=en&token=_REDACTED_"
    )
    assert result.dropped_fragment is True
    assert result.redacted_keys == ("token",)


@pytest.mark.unit
def test_sanitize_url_rewrites_sensitive_path_segments():
    result = sanitize_url(
        "https://example.com/users/john@example.com/550e8400-e29b-41d4-a716-446655440000"
    )

    assert result.sanitized_url == "https://example.com/users/[EMAIL]/[UUID]"
    assert result.dropped_fragment is False
    assert result.redacted_keys == ()


@pytest.mark.unit
def test_sanitize_url_sorts_query_keys_for_stability():
    result = sanitize_url("https://example.com/search?z=1&a=2")

    assert result.sanitized_url == "https://example.com/search?a=2&z=1"
    assert result.redacted_keys == ()


@pytest.mark.unit
def test_sanitize_url_redacts_sensitive_looking_value_even_with_generic_key():
    result = sanitize_url(
        "https://example.com/cb?state=ok&q=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa.bbb"
    )

    assert result.sanitized_url == "https://example.com/cb?q=_REDACTED_&state=ok"
    assert result.redacted_keys == ("q",)


@pytest.mark.unit
def test_sanitize_url_uses_root_path_when_missing():
    result = sanitize_url("https://example.com")

    assert result.sanitized_url == "https://example.com/"
    assert result.dropped_fragment is False
    assert result.redacted_keys == ()


@pytest.mark.unit
def test_sanitize_url_redacts_embedded_encoded_url_value():
    result = sanitize_url(
        "https://example.com/cb?foo=https%3A%2F%2Fna.primevideo.com%2Fauth%2Freturn&lang=en"
    )

    assert result.sanitized_url == "https://example.com/cb?foo=_REDACTED_&lang=en"
    assert result.redacted_keys == ("foo",)


@pytest.mark.unit
def test_realistic_amazon_signin_shape():
    result = sanitize_url(
        "https://www.amazon.ca/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fna.primevideo.com%2Fauth%2Freturn%2Fref%3Dav_auth_ap%3F_t%3DfakeTraceToken1234567890abcdef&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=amzn_prime_video_sso_ca&openid.mode=checkid_setup&countryCode=CA&siteState=999-1234567-7654321&language=en_US&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
    )

    assert result.sanitized_url == (
        "https://www.amazon.ca/ap/signin?countryCode=_REDACTED_&language=en_US&"
        "openid.assoc_handle=amzn_prime_video_sso_ca&openid.claimed_id=_REDACTED_&"
        "openid.identity=_REDACTED_&openid.mode=checkid_setup&openid.ns=_REDACTED_&"
        "openid.pape.max_auth_age=_REDACTED_&openid.return_to=_REDACTED_&"
        "siteState=999-1234567-7654321"
    )
    assert result.redacted_keys == (
        "countryCode",
        "openid.claimed_id",
        "openid.identity",
        "openid.ns",
        "openid.pape.max_auth_age",
        "openid.return_to",
    )


@pytest.mark.unit
def test_realistic_banking_uuid_redaction():
    result = sanitize_url(
        "https://www1.bmo.com/banking/digital/account-details/cc/111bbb22-1a2b-11f2-1111-111f11cfb2a3"
    )
    assert (
        result.sanitized_url
        == "https://www1.bmo.com/banking/digital/account-details/cc/[UUID]"
    )
    assert result.dropped_fragment is False
    assert result.redacted_keys == ()


@pytest.mark.unit
def test_payments_url_redacts_multiple_long_compact_token_like_values():
    result = sanitize_url(
        "https://payments.google.com/gp/w/home/accountdetail?ebaid=ZZ9xFAKEpL2QnR7VmTk83zQwX4NsHdJf%2F7kLmNoPq%2Bu8sTyVw44AaBbC3%2FDdEeFfGgHhIiJjKk&ec=YY7mTESTuR4QwE9TyUiOpAsDfGh%2FjKlZxCvBnMqWeRtYuIoPaSdFgHjKlQwErTyUiOpAsDfGh"
    )

    assert result.sanitized_url == (
        "https://payments.google.com/gp/w/home/accountdetail?ebaid=_REDACTED_&ec=_REDACTED_"
    )
    assert result.redacted_keys == ("ebaid", "ec")


@pytest.mark.unit
def test_openai_callback_redacts_code_and_state_with_synthetic_values():
    result = sanitize_url(
        "https://platform.openai.com/auth/callback?code=ac_FAKEAuthCodeTokenForTestingOnly_AbCdEf1234567890.XyZ9876543210_FakeSegment&scope=openid+profile+email+offline_access&state=ZmFrZV9zdGF0ZV90b2tlbl9mb3JfdGVzdGluZ19vbmx5XzEyMzQ1Njc4OTA%3D"
    )

    assert result.sanitized_url == (
        "https://platform.openai.com/auth/callback?code=_REDACTED_&"
        "scope=openid+profile+email+offline_access&state=_REDACTED_"
    )
    assert result.redacted_keys == ("code", "state")
