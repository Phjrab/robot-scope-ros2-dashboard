#!/usr/bin/env bash
set -euo pipefail

connection_name="Wired connection 1"
interface_name="eno1"
address="192.168.123.99/24"

nmcli connection modify "$connection_name" \
  ipv4.method manual \
  ipv4.addresses "$address" \
  ipv4.gateway "" \
  ipv4.dns "" \
  ipv4.never-default yes \
  connection.autoconnect yes
nmcli connection up "$connection_name"

ip -br addr show "$interface_name"
nmcli -g GENERAL.STATE device show "$interface_name"
