#!/usr/bin/env bash

set -euo pipefail

# This fixture runs only in a disposable container with its own network namespace.
table="ci_net_${BASHPID}"
interface=ci_net_dummy
table_created=0
interface_created=0

cleanup() {
	local status=$?
	trap - EXIT
	if ((table_created)); then
		nft delete table inet "$table" || status=1
	fi
	if ((interface_created)); then
		ip link delete "$interface" || status=1
	fi
	exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ip link add "$interface" type dummy
interface_created=1
ip address add 198.51.100.1/24 dev "$interface"
ip link set "$interface" up
ip -j route show 198.51.100.0/24 | python3 -c '
import json, sys
routes = json.load(sys.stdin)
assert len(routes) == 1 and routes[0]["dev"] == "ci_net_dummy"
'
ping -c 1 -W 2 -w 5 198.51.100.1 >/dev/null

nft add table inet "$table"
table_created=1
nft add chain inet "$table" input '{ type filter hook input priority 0; policy accept; }'
nft add rule inet "$table" input ip daddr 198.51.100.1 icmp type echo-request counter drop
if ping -c 1 -W 1 -w 2 198.51.100.1 >/dev/null; then
	printf 'test-owned nftables rule did not block test traffic\n' >&2
	exit 1
fi
nft -j list table inet "$table" | python3 -c '
import json, sys
rules = [entry["rule"] for entry in json.load(sys.stdin)["nftables"] if "rule" in entry]
assert any(expr.get("counter", {}).get("packets", 0) > 0 for rule in rules for expr in rule["expr"])
'

if [[ ${CI_NET_INJECT_FAILURE:-0} == 1 ]]; then
	printf 'injected failure after network setup\n' >&2
	exit 23
fi

nft delete table inet "$table"
table_created=0
ping -c 1 -W 2 -w 5 198.51.100.1 >/dev/null
printf 'test-owned rules, interface, route, and traffic verified\n'
