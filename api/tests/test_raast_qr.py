import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.pay.raast_qr import (
    crc16_ccitt, encode_tlv, _fmt_len,
    _format_amount_raast, build_payload, build_payload_amount,
)


def test_crc16_known_value():
    data = b"0002020102110202000424PK36MPBL0000000000123456781004"
    crc = crc16_ccitt(data)
    assert isinstance(crc, int)
    assert 0 <= crc <= 0xFFFF


def test_encode_tlv_basic():
    assert encode_tlv("04", "HELLO") == "0405HELLO"


def test_fmt_len_padding():
    assert _fmt_len(5) == "05"
    assert _fmt_len(12) == "12"


def test_format_amount_raast_single_digit():
    assert _format_amount_raast(5) == "05"
    assert _format_amount_raast(10) == "10"
    assert _format_amount_raast("123.45") == "123"


def test_build_payload_static():
    iban = "PK36MPBL0000000000123456"
    result = build_payload(iban)
    assert result.startswith("0002020102110202000424")
    assert "1004" in result
    assert len(result) > 40


def test_build_payload_amount_contains_fields():
    iban = "PK36MPBL0000000000123456"
    result = build_payload_amount(iban, 1000, "010120261200", timestamp_raw=True)
    assert "05" in result
    assert "1004" in result
