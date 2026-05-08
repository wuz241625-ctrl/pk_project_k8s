"""Raast QR payload encoding utilities — pure functions, zero external deps."""

import datetime
from decimal import Decimal, InvalidOperation
from datetime import timezone, timedelta
from typing import Dict, Optional, Union


def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """计算CRC-16/CCITT-FALSE校验和 - 匹配Java实现"""
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def _fmt_len(n: int) -> str:
    if n < 0 or n > 99:
        raise ValueError(f"Length out of range for 2 digits: {n}")
    return f"{n:02d}"

def encode_tlv(tag: str, value: str) -> str:
    if len(tag) != 2 or not tag.isdigit():
        raise ValueError(f"Invalid tag: {tag}")
    ln = _fmt_len(len(value))
    return f"{tag}{ln}{value}"


def _format_timestamp(ts: Union[int, float, str, datetime.datetime]) -> str:
    """Format timestamp to ddMMyyyyHHmm.

    Accepts:
    - int/float: UNIX seconds
    - datetime: naive => treated as local time; aware => used as-is
    - str: if 12 digits, assumed ddMMyyyyHHmm; if 10/13 digits, treated as UNIX seconds
    """
    pkt = timezone(timedelta(hours=5))
    if isinstance(ts, (int, float)):
        dt = datetime.datetime.fromtimestamp(ts, tz=pkt)
    elif isinstance(ts, datetime.datetime):
        dt = ts.astimezone(pkt) if ts.tzinfo is not None else ts.replace(tzinfo=pkt)
    elif isinstance(ts, str):
        s = ts.strip()
        if len(s) == 12 and s.isdigit():
            return s
        # Try epoch seconds/millis
        if s.isdigit() and len(s) in (10, 13):
            sec = int(s[:10])
            dt = datetime.datetime.fromtimestamp(sec, tz=pkt)
        else:
            # Try flexible parse: ddMMyyyyHHmm
            try:
                return datetime.datetime.strptime(s, "%d%m%Y%H%M").strftime("%d%m%Y%H%M")
            except Exception as e:
                raise ValueError(f"Unrecognized timestamp string: {ts}") from e
    else:
        raise TypeError("Unsupported timestamp type")
    return dt.strftime("%d%m%Y%H%M")


def _format_amount_raast(value: Union[int, float, str]) -> str:
    """Normalize amount to match the Android implementation:

    - Coerce to integer (drop fractional part, like parseInt in Android).
    - Left-pad a single-digit amount with a leading zero (e.g., 5 -> "05").
    - Return as string to be used as the TLV value for tag 05.
    """
    # Convert to integer similar to Java's Integer.parseInt on the displayed amount
    if isinstance(value, int):
        n = value
    else:
        s = str(value).strip()
        # Remove common formatting, if present
        s = s.replace(",", "")
        # Try Decimal to support inputs like "10.00"
        try:
            n = int(Decimal(s))
        except (InvalidOperation, ValueError):
            # Fallback: keep only leading integer part
            try:
                n = int(float(s))
            except Exception as e:
                raise ValueError(f"Invalid amount: {value}") from e
    amt_str = str(n)
    if n < 10:
        amt_str = "0" + amt_str
    return amt_str

def build_payload(
    iban: str,
    *,
    crc_tag: str = "10",
    base_fields: Optional[Dict[str, str]] = None,
) -> str:
    """Build a static QR payload (no amount/timestamp).

    Structure: 00-01-02-04-10(CRC). Matches sample:
      0002020102110202000424<IBAN>1004<CRC>

    Defaults:
    - 00 = '02'
    - 01 = '11' (static)
    - 02 = '00'
    - 04 = IBAN (variable length)
    - 10 = CRC (computed, length 04)
    """
    fields: Dict[str, str] = {
        "00": "02",
        "01": "11",
        "02": "00",
        "04": str(iban),
    }
    if base_fields:
        fields.update({k: str(v) for k, v in base_fields.items()})

    order = ["00", "01", "02", "04"]
    payload_wo_crc = "".join(encode_tlv(t, fields[t]) for t in order if t in fields)
    base_for_crc = payload_wo_crc + f"{crc_tag}04"
    crc_val = f"{crc16_ccitt(base_for_crc.encode('utf-8')):04X}"
    return base_for_crc + crc_val

def build_payload_amount(
    iban: str,
    amount: Union[int, float, str],
    timestamp: Union[int, float, str, datetime.datetime],
    *,
    crc_tag: str = "10",
    base_fields: Optional[Dict[str, str]] = None,
    timestamp_raw: bool = False,
) -> str:
    """Build a new payload by filling IBAN(tag 04), amount(tag 05), timestamp(tag 07).

    - Preserves default static fields: tag 00='02', 01='12', 02='00' unless overridden via base_fields.
    - Recomputes CRC at the end using crc_tag (default '10').
    - Amount is converted to string as-is; for decimals like 123.45 pass a preformatted string if needed.
    """
    # Base defaults from the provided sample
    fields: Dict[str, str] = {
        "00": "02",
        "01": "12",
        "02": "00",
    }
    if base_fields:
        fields.update({k: str(v) for k, v in base_fields.items()})

    fields["04"] = str(iban)
    # Match Android behavior for amount formatting
    fields["05"] = _format_amount_raast(amount)
    fields["07"] = str(timestamp) if timestamp_raw else _format_timestamp(timestamp)

    # Preserve order similar to sample
    order = ["00", "01", "02", "04", "05", "07"]
    payload_wo_crc = "".join(encode_tlv(t, fields[t]) for t in order if t in fields)
    # Append CRC tag+len (without value) to compute CRC over
    base_for_crc = payload_wo_crc + f"{crc_tag}04"
    # Android uses UTF-8 getBytes; calculate CRC-16/CCITT-FALSE to match Java implementation
    crc_val = f"{crc16_ccitt(base_for_crc.encode('utf-8')):04X}"
    return base_for_crc + crc_val
