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


def test_removed_states_absent():
    """spec §6.1：老状态必须删除。"""
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOAD_REQUIRED')
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOADED')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_READY')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_PASSED')
    # LOGIN_SUCCESSFUL 是别名，也删
    assert not hasattr(LoginStatus, 'LOGIN_SUCCESSFUL')


from unittest.mock import MagicMock
from application.app.login.banks.easypaisa import EasyPaisa
from application.lakshmi_api.exceptions.api_error import NewApiError


@pytest.fixture
def ep_for_transition():
    handler = MagicMock()
    return EasyPaisa(handler)


def test_assert_transition_allows_valid(ep_for_transition):
    session = {'status': LoginStatus.OTP_SENT}
    ep_for_transition._assert_status_transition(
        session, LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED, 'test'
    )


def test_assert_transition_rejects_invalid(ep_for_transition):
    session = {'status': LoginStatus.OTP_SENT}
    with pytest.raises(NewApiError) as exc:
        ep_for_transition._assert_status_transition(
            session, LoginStatus.OTP_SENT, LoginStatus.ACTIVE_SUCCESSFUL, 'test'
        )
    assert exc.value.code == 'INVALID_TRANSITION'


def test_assert_transition_pre_login_to_account_selection(ep_for_transition):
    """二次上号跨步要被允许。"""
    session = {'status': LoginStatus.PRE_LOGIN_CREATED}
    ep_for_transition._assert_status_transition(
        session, LoginStatus.PRE_LOGIN_CREATED, LoginStatus.ACCOUNT_SELECTION_REQUIRED, 'test'
    )


def test_awaiting_pin_change_transitions_to_account_selection():
    """hotfix-2 P0: change_pin 完成后直接进入 ACCOUNT_SELECTION_REQUIRED（不再经 FINGERPRINT_VERIFIED）。"""
    targets = STATUS_TRANSITIONS[LoginStatus.AWAITING_PIN_CHANGE]
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED in targets, \
        'AWAITING_PIN_CHANGE 必须能转到 ACCOUNT_SELECTION_REQUIRED'
    assert LoginStatus.FINGERPRINT_VERIFIED not in targets, \
        'P0 改造：不再保留 AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED 边'
    assert LoginStatus.NEEDS_RELOGIN in targets, '终态逃生门仍保留'
