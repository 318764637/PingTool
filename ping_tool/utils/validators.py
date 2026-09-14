import ipaddress
import re

# 完整域名：多标签，末标签（TLD）为 ≥2 个字母
DOMAIN_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$"
)

# 单标签本地主机名：localhost、myhost 等
LOCALNAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
)

# 保留地址按「网段语义」判定（而非字符串精确匹配），避免等价写法绕过：
#   0.0.0.0/8      本网络（含 0.0.0.0）
#   127.0.0.0/8    环回（含 127.0.0.1）
#   224.0.0.0/4    组播
#   240.0.0.0/4    保留（含 255.255.255.255 广播）
#   ::/128         IPv6 未指定地址
#   ::1/128        IPv6 环回
#   ff00::/8       IPv6 组播
# 不使用 is_private / is_reserved：其语义随 Python 版本变化，
# 且会把文档地址、NAT64 等合法目标一并拒绝。
RESERVED_NETWORKS = (
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv4Network("240.0.0.0/4"),
    ipaddress.IPv6Network("::/128"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("ff00::/8"),
)


def _strip_zone(ip):
    """剥离 IPv6 接口标识（fe80::1%eth0 → fe80::1），非法输入返回 None。"""
    if "%" not in ip:
        return ip
    base, _, zone = ip.partition("%")
    if not base or not zone:
        return None
    return base


def _parse_address(target):
    """把目标解析为 ipaddress 地址对象（支持 zone id）；非 IP 返回 None。"""
    base = _strip_zone(target)
    if base is None:
        return None
    try:
        return ipaddress.ip_address(base)
    except ValueError:
        return None


def _is_reserved_address(addr):
    """判断地址是否属于禁止添加的保留/组播网段（IPv4-mapped 递归判定）。"""
    if any(addr in network for network in RESERVED_NETWORKS):
        return True
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None:
            return _is_reserved_address(mapped)
    return False


def validate_ipv4(ip):
    """校验 IPv4 地址（拒绝前导零，如 08.8.8.8）。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return isinstance(addr, ipaddress.IPv4Address)


def validate_ipv6(ip):
    """校验 IPv6 地址，支持 :: 压缩、IPv4-mapped、zone id。"""
    base = _strip_zone(ip)
    if base is None:
        return False
    try:
        addr = ipaddress.ip_address(base)
    except ValueError:
        return False
    return isinstance(addr, ipaddress.IPv6Address)


def validate_domain(domain):
    """校验域名（完整域名或单标签本地主机名）。"""
    if len(domain) > 253:
        return False
    if LOCALNAME_PATTERN.match(domain):
        return True
    return bool(DOMAIN_PATTERN.match(domain))


def validate_target(target):
    if not isinstance(target, str) or not target.strip():
        return False, "目标不能为空"

    target = target.strip()

    address = _parse_address(target)
    if address is not None:
        # 判定前先解析成地址对象：0:0:0:0:0:0:0:1、0000::1 等等价写法同样被识别
        if _is_reserved_address(address):
            return False, "不能使用保留地址"
        return True, ""

    # 单标签主机名（localhost、myhost）；纯数字单标签不是合法主机名，
    # 通常是用户把 IP 写错（如 999），直接拒绝而不是留给 ping 去报错
    if validate_domain(target) and not target.isdigit():
        return True, ""

    return False, "请输入有效的 IP 地址或域名"


def sanitize_target(target):
    """清理目标：去除首尾空格；IP 规范化为标准形式（IPv6 压缩 + 小写）；
    域名转小写。zone id（如 %eth0）原样保留。"""
    if not isinstance(target, str):
        return ""
    target = target.strip()
    if not target:
        return target

    base, sep, zone = target.partition("%") if "%" in target else (target, "", "")
    try:
        addr = ipaddress.ip_address(base) if base else None
    except ValueError:
        addr = None

    if addr is not None:
        # IP：规范化（统一小写 + IPv6 压缩），zone id 大小写敏感故保留
        return f"{addr.compressed}%{zone}" if sep else addr.compressed
    # 域名：转小写
    return target.lower()
