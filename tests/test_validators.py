"""validators 模块单元测试。"""
import pytest

from ping_tool.utils.validators import (
    validate_ipv4,
    validate_ipv6,
    validate_domain,
    validate_target,
    sanitize_target,
)


class TestValidateIpv4:
    def test_valid(self):
        assert validate_ipv4("8.8.8.8") is True
        assert validate_ipv4("192.168.0.1") is True
        assert validate_ipv4("0.0.0.0") is True  # 语法合法，保留与否由 validate_target 决定

    def test_reject_leading_zero(self):
        assert validate_ipv4("08.8.8.8") is False

    def test_reject_out_of_range(self):
        assert validate_ipv4("999.1.1.1") is False
        assert validate_ipv4("256.0.0.1") is False

    def test_reject_wrong_segment_count(self):
        assert validate_ipv4("1.2.3") is False
        assert validate_ipv4("1.2.3.4.5") is False

    def test_reject_non_ip(self):
        assert validate_ipv4("baidu.com") is False
        assert validate_ipv4("") is False


class TestValidateIpv6:
    def test_full_form(self):
        assert validate_ipv6("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True

    def test_compressed(self):
        assert validate_ipv6("::1") is True
        assert validate_ipv6("fe80::1") is True
        assert validate_ipv6("2001:db8::1") is True

    def test_ipv4_mapped(self):
        assert validate_ipv6("::ffff:1.2.3.4") is True

    def test_zone_id(self):
        assert validate_ipv6("fe80::1%eth0") is True
        assert validate_ipv6("fe80::1%12") is True

    def test_reject_invalid(self):
        assert validate_ipv6("::1::2") is False
        assert validate_ipv6("12345::") is False
        assert validate_ipv6("8.8.8.8") is False
        assert validate_ipv6("") is False


class TestValidateDomain:
    def test_full_domain(self):
        assert validate_domain("baidu.com") is True
        assert validate_domain("www.example.co.uk") is True
        assert validate_domain("a-b.example.com") is True

    def test_single_label_local(self):
        assert validate_domain("localhost") is True
        assert validate_domain("myhost") is True

    def test_reject(self):
        assert validate_domain("-bad.com") is False
        assert validate_domain("bad-.com") is False
        assert validate_domain("a..b") is False
        assert validate_domain("") is False


class TestValidateTarget:
    def test_ipv4(self):
        ok, msg = validate_target("8.8.8.8")
        assert ok and msg == ""

    def test_ipv6(self):
        ok, _ = validate_target("::1")
        assert not ok  # 保留地址
        ok, _ = validate_target("2001:db8::1")
        assert ok

    def test_domain(self):
        ok, _ = validate_target("localhost")
        assert ok

    def test_reserved(self):
        for ip in ("0.0.0.0", "255.255.255.255", "127.0.0.1", "::1"):
            ok, msg = validate_target(ip)
            assert not ok
            assert "保留" in msg

    def test_invalid(self):
        ok, _ = validate_target("08.8.8.8")
        assert not ok
        ok, _ = validate_target("999.1.1.1")
        assert not ok
        ok, _ = validate_target("")
        assert not ok
        ok, _ = validate_target("   ")
        assert not ok

    def test_no_exception_on_garbage(self):
        for bad in (None, 123, ["x"], "not an ip!", "abc..def"):
            try:
                ok = validate_target(bad)
                assert isinstance(ok, tuple)
            except (TypeError, ValueError, AttributeError):
                pytest.fail(f"validate_target({bad!r}) 不应抛异常")


class TestSanitizeTarget:
    def test_strip_and_lowercase_domain(self):
        assert sanitize_target("  BAIDU.COM  ") == "baidu.com"

    def test_ip_unchanged(self):
        assert sanitize_target("  8.8.8.8  ") == "8.8.8.8"

    def test_ipv6_unchanged(self):
        # IP 规范化为标准形式：小写 + 压缩；zone id 大小写敏感保留
        assert sanitize_target("FE80::1") == "fe80::1"
        assert sanitize_target("2001:0DB8:0:0:0:0:0:1") == "2001:db8::1"
        assert sanitize_target("fe80::1%eth0") == "fe80::1%eth0"
        assert sanitize_target("FE80::1%eth0") == "fe80::1%eth0"

    def test_empty(self):
        assert sanitize_target("") == ""
        assert sanitize_target("   ") == ""


class TestReservedAddressSemantics:
    """保留地址按网段语义判定：等价写法（压缩/未压缩、IPv4-mapped）不得绕过。"""

    def test_equivalent_spellings_rejected(self):
        for target in (
            "0:0:0:0:0:0:0:1",  # ::1 的完整写法
            "0000::1",          # ::1 的前导零写法
            "::",               # IPv6 未指定地址
            "::ffff:127.0.0.1",  # IPv4-mapped 环回
        ):
            ok, msg = validate_target(target)
            assert not ok, f"{target} 应被拒绝"
            assert "保留" in msg

    def test_reserved_networks_rejected(self):
        for target in (
            "0.1.2.3",        # 0.0.0.0/8 本网络
            "127.0.0.2",      # 环回网段其他地址
            "224.0.0.1",      # 组播
            "240.0.0.1",      # 保留段
            "ff02::1",        # IPv6 组播
        ):
            ok, _ = validate_target(target)
            assert not ok, f"{target} 应被拒绝"

    def test_legitimate_addresses_still_accepted(self):
        for target in (
            "8.8.8.8",
            "100.101.102.103",  # Tailscale 分配段（100.64.0.0/10）
            "192.168.1.1",
            "169.254.1.1",     # 链路本地：用户可能需要
            "2001:db8::1",
            "fe80::1%12",      # 带接口标识的链路本地
            "::ffff:8.8.8.8",  # IPv4-mapped 公网地址
            "localhost",
            "myhost",          # 单标签主机名
            "baidu.com",
        ):
            ok, msg = validate_target(target)
            assert ok, f"{target} 应被接受，实际: {msg}"

    def test_all_numeric_single_label_rejected(self):
        # 纯数字单标签不是合法主机名，通常是 IP 写错（如 999）
        for target in ("999", "12345"):
            ok, msg = validate_target(target)
            assert not ok
            assert "有效" in msg
