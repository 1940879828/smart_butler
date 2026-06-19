#!/bin/bash
# 验证 Ubuntu 与 Windows 机器的网络连通性

WINDOWS_IP="192.168.2.xxx"  # 替换为实际 IP

echo "=== 网络连通性检查 ==="

# ICMP 测试
echo -n "Ping 测试: "
if ping -c 1 -W 2 $WINDOWS_IP &>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达，请检查网络和防火墙"
fi

# 数据库端口测试 (PostgreSQL 默认 5432)
echo -n "PostgreSQL (5432): "
if timeout 2 bash -c "echo > /dev/tcp/$WINDOWS_IP/5432" 2>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达，请检查 Windows 上 PostgreSQL 是否运行且允许外部连接"
fi

# Ollama 端口测试 (默认 11434)
echo -n "Ollama (11434): "
if timeout 2 bash -c "echo > /dev/tcp/$WINDOWS_IP/11434" 2>/dev/null; then
    echo "✓ 可达"
else
    echo "✗ 不可达"
fi
