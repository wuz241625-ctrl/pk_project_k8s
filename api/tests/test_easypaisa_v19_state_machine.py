"""验证 v1.9 8 状态机的邻接表语义。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.app.login.banks.easypaisa import LoginStatus, STATUS_TRANSITIONS


def test_eight_states_defined():
    """8 状态全部定义且字符串值符合 APP 契约。"""
    assert LoginStatus.PRE_LOGIN_CREATED == "preLoginCreated"
    assert LoginStatus.OTP_SENT == "otpSent"
    assert LoginStatus.OTP_VERIFIED == "otpVerified"
    assert LoginStatus.FINGERPRINT_VERIFIED == "fingerprintVerified"
    assert LoginStatus.AWAITING_PIN_CHANGE == "awaitingPinChange"
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED == "accountSelectionRequired"
    assert LoginStatus.ACTIVE_SUCCESSFUL == "activeSuccessful"
    assert LoginStatus.NEEDS_RELOGIN == "needsRelogin"


def test_terminal_states_have_no_outgoing():
    assert STATUS_TRANSITIONS[LoginStatus.ACTIVE_SUCCESSFUL] == []
    assert STATUS_TRANSITIONS[LoginStatus.NEEDS_RELOGIN] == []


def test_all_non_terminal_can_reach_needs_relogin():
    """所有非终态都能跳到 NEEDS_RELOGIN（统一逃生门）。"""
    non_terminal = [
        LoginStatus.PRE_LOGIN_CREATED,
        LoginStatus.OTP_SENT,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
    ]
    for status in non_terminal:
        assert LoginStatus.NEEDS_RELOGIN in STATUS_TRANSITIONS[status], \
            f"{status} cannot transition to NEEDS_RELOGIN"


def test_pre_login_cross_step_edges():
    """spec §3.1.1：pre_login 内部续推支持跨步。"""
    pre = STATUS_TRANSITIONS[LoginStatus.PRE_LOGIN_CREATED]
    assert LoginStatus.OTP_SENT in pre              # 首次
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED in pre  # 二次续推全成功
    assert LoginStatus.OTP_VERIFIED in pre          # 二次指纹失败借位
    assert LoginStatus.AWAITING_PIN_CHANGE in pre   # 二次续推遇 PIN 需改


def test_otp_sent_cross_step_edges():
    otp_sent = STATUS_TRANSITIONS[LoginStatus.OTP_SENT]
    assert LoginStatus.OTP_VERIFIED in otp_sent
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED in otp_sent  # fallback 续推全成功
    assert LoginStatus.PRE_LOGIN_CREATED in otp_sent           # URM90040 reset


def test_awaiting_pin_change_returns_to_fingerprint_verified():
    transitions = STATUS_TRANSITIONS[LoginStatus.AWAITING_PIN_CHANGE]
    assert LoginStatus.FINGERPRINT_VERIFIED in transitions


def test_removed_states_absent():
    """spec §6.1：老状态必须删除。"""
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOAD_REQUIRED')
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOADED')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_READY')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_PASSED')
    # LOGIN_SUCCESSFUL 是别名，也删
    assert not hasattr(LoginStatus, 'LOGIN_SUCCESSFUL')
