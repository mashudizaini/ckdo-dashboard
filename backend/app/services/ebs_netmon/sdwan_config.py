"""
SD-WAN configuration viewer — reads (never writes) the running SD-WAN, IPsec,
static route and shaping configuration of the HO and Plant FortiGates over
the same read-only SSH login as fortigate.py, parses the FortiOS `show`
output into a tree, and checks it against the CKDO SD-WAN runbook.

The one question this module exists to answer: does an EBS session keep ONE
tunnel for both directions? SD-WAN rules only steer the side that opens a
session — HO-opened EBS sessions are steered by FGT HO, and FGT Plant replies
along the session — so the checks compare the two sides' member order, SLA
thresholds and timers for the EBS rule, pairing tunnels by their public
endpoints.

`show full-configuration` is used for SD-WAN and IPsec so every value shown is
what the box runs, not an assumed FortiOS default. Secrets (psksecret and any
`ENC ...` value) are redacted before anything is parsed or stored.
"""
import ipaddress
import re
import shlex

from app.services import it_monitoring_store as store
from app.services.ebs_netmon import fortigate

COMMANDS = [
    ("status", "get system status"),
    ("sdwan", "show full-configuration system sdwan"),
    ("phase1", "show full-configuration vpn ipsec phase1-interface"),
    ("phase2", "show full-configuration vpn ipsec phase2-interface"),
    ("interface", "show system interface"),
    ("static", "show router static"),
    ("settings", "show system settings"),
    ("address", "show firewall address"),
    ("addrgrp", "show firewall addrgrp"),
    ("shaper", "show firewall shaper traffic-shaper"),
    ("shaping", "show firewall shaping-policy"),
    ("sdwan_member", "diagnose sys sdwan member"),
    ("sdwan_service", "diagnose sys sdwan service"),
    ("sdwan_health", "diagnose sys sdwan health-check"),
]

_SECRET_KEY = re.compile(r"^(\s*set\s+)(\S*(?:secret|passw|psk|private-key|auth-key|md5-key)\S*)(\s+).*$", re.I)
_ENC = re.compile(r"(\bENC\s+)\S+")


def redact(text: str) -> str:
    out = []
    for line in (text or "").splitlines():
        line = _SECRET_KEY.sub(r"\1\2\3<disembunyikan>", line)
        out.append(_ENC.sub(r"\1<disembunyikan>", line))
    return "\n".join(out)


# ── FortiOS config tree ────────────────────────────────────────────────────

def parse_config(text: str) -> dict:
    """`config X / edit Y / set k v / next / end` → nested dicts. Table rows
    live under "_entries" (insertion order = CLI order, which matters for
    SD-WAN services). A `set` with one value is a str, with more a list."""
    root: dict = {}
    stack = [root]
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            tok = shlex.split(s, posix=True)
        except ValueError:
            tok = s.split()
        if not tok:
            continue
        cmd, cur = tok[0], stack[-1]
        if cmd == "config" and len(tok) > 1:
            stack.append(cur.setdefault(" ".join(tok[1:]), {}))
        elif cmd == "edit" and len(tok) > 1:
            stack.append(cur.setdefault("_entries", {}).setdefault(tok[1], {}))
        elif cmd in ("next", "end"):
            if len(stack) > 1:
                stack.pop()
        elif cmd == "set" and len(tok) >= 2:
            vals = tok[2:]
            cur[tok[1]] = vals[0] if len(vals) == 1 else (vals or "")
    return root


def _entries(node) -> list[tuple[str, dict]]:
    return list(((node or {}).get("_entries") or {}).items())


def _list(v) -> list[str]:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def _str(v) -> str | None:
    if v is None or v == "":
        return None
    return " ".join(v) if isinstance(v, list) else v


def _int(v):
    try:
        return int(_str(v))
    except (TypeError, ValueError):
        return None


def _block(raw: dict, key: str, name: str) -> dict:
    return parse_config(raw.get(key, "")).get(name, {})


def _mask_to_net(ip_mask) -> ipaddress.IPv4Network | None:
    """["10.0.0.1", "255.255.255.0"] or "10.0.0.1 255.255.255.0" → network."""
    parts = ip_mask.split() if isinstance(ip_mask, str) else _list(ip_mask)
    if not parts:
        return None
    try:
        if len(parts) >= 2:
            return ipaddress.IPv4Network(f"{parts[0]}/{parts[1]}", strict=False)
        return ipaddress.IPv4Network(parts[0], strict=False)
    except ValueError:
        return None


# ── Normalise one FortiGate ────────────────────────────────────────────────

def normalize(raw: dict) -> dict:
    sd = _block(raw, "sdwan", "system sdwan")
    members = [{
        "seq": _int(k), "interface": _str(v.get("interface")), "zone": _str(v.get("zone")),
        "gateway": _str(v.get("gateway")), "source": _str(v.get("source")),
        "priority": _int(v.get("priority")), "cost": _int(v.get("cost")), "weight": _int(v.get("weight")),
        "status": _str(v.get("status")) or "enable", "comment": _str(v.get("comment")),
    } for k, v in _entries(sd.get("members"))]

    health = []
    for name, v in _entries(sd.get("health-check")):
        health.append({
            "name": name, "server": _list(v.get("server")), "protocol": _str(v.get("protocol")),
            "port": _int(v.get("port")), "interval_ms": _int(v.get("interval")),
            "probe_timeout_ms": _int(v.get("probe-timeout")), "failtime": _int(v.get("failtime")),
            "recoverytime": _int(v.get("recoverytime")), "update_static_route": _str(v.get("update-static-route")),
            "members": [_int(m) for m in _list(v.get("members"))],
            "sla": [{
                "id": _int(sid), "link_cost_factor": _list(s.get("link-cost-factor")),
                "latency_ms": _int(s.get("latency-threshold")), "jitter_ms": _int(s.get("jitter-threshold")),
                "loss_pct": _int(s.get("packetloss-threshold")),
            } for sid, s in _entries(v.get("sla"))],
        })

    services = []
    for k, v in _entries(sd.get("service")):
        services.append({
            "id": _int(k), "name": _str(v.get("name")), "mode": _str(v.get("mode")) or "manual",
            "status": _str(v.get("status")) or "enable",
            "src": _list(v.get("src")), "dst": _list(v.get("dst")),
            "src_negate": _str(v.get("src-negate")) == "enable", "dst_negate": _str(v.get("dst-negate")) == "enable",
            "internet_service": _str(v.get("internet-service")) == "enable",
            "protocol": _int(v.get("protocol")), "start_port": _int(v.get("start-port")), "end_port": _int(v.get("end-port")),
            "priority_members": [_int(m) for m in _list(v.get("priority-members"))],
            "priority_zone": _list(v.get("priority-zone")),
            "health_check": _list(v.get("health-check")),
            # Rows are keyed by the health-check name: edit "HC-OVERLAY" / set id 1
            "sla": [{"health_check": hc, "id": _int(s.get("id"))} for hc, s in _entries(v.get("sla"))],
            "sla_compare_method": _str(v.get("sla-compare-method")),
            "hold_down_time": _int(v.get("hold-down-time")),
            "tie_break": _str(v.get("tie-break")),
        })

    ifaces = {}
    for name, v in _entries(_block(raw, "interface", "system interface")):
        ifaces[name] = {
            "name": name, "alias": _str(v.get("alias")), "type": _str(v.get("type")) or "physical",
            "role": _str(v.get("role")), "mode": _str(v.get("mode")), "ip": _str(v.get("ip")),
            "remote_ip": _str(v.get("remote-ip")), "parent": _str(v.get("interface")),
            "status": _str(v.get("status")) or "up", "description": _str(v.get("description")),
            "allowaccess": _list(v.get("allowaccess")),
            "preserve_session_route": _str(v.get("preserve-session-route")) or "disable",
        }

    def wan_ip(iface: str | None) -> str | None:
        ip = (ifaces.get(iface or "") or {}).get("ip")
        return ip.split()[0] if ip else None

    phase1 = [{
        "name": n, "interface": _str(v.get("interface")), "local_ip": wan_ip(_str(v.get("interface"))),
        "type": _str(v.get("type")), "remote_gw": _str(v.get("remote-gw")),
        "ike_version": _str(v.get("ike-version")), "proposal": _list(v.get("proposal")),
        "dhgrp": _list(v.get("dhgrp")), "dpd": _str(v.get("dpd")),
        "dpd_retryinterval": _str(v.get("dpd-retryinterval")), "dpd_retrycount": _int(v.get("dpd-retrycount")),
        "nattraversal": _str(v.get("nattraversal")), "net_device": _str(v.get("net-device")),
        "add_route": _str(v.get("add-route")), "keylife": _int(v.get("keylife")),
        "auto_discovery_sender": _str(v.get("auto-discovery-sender")),
        "tunnel_ip": (ifaces.get(n) or {}).get("ip"), "tunnel_remote_ip": (ifaces.get(n) or {}).get("remote_ip"),
        "preserve_session_route": (ifaces.get(n) or {}).get("preserve_session_route", "disable"),
    } for n, v in _entries(_block(raw, "phase1", "vpn ipsec phase1-interface"))]

    phase2 = [{
        "name": n, "phase1name": _str(v.get("phase1name")), "proposal": _list(v.get("proposal")),
        "dhgrp": _list(v.get("dhgrp")), "pfs": _str(v.get("pfs")),
        "auto_negotiate": _str(v.get("auto-negotiate")), "keepalive": _str(v.get("keepalive")),
        "keylifeseconds": _int(v.get("keylifeseconds")),
        "src": _str(v.get("src-subnet")) or _str(v.get("src-name")), "dst": _str(v.get("dst-subnet")) or _str(v.get("dst-name")),
    } for n, v in _entries(_block(raw, "phase2", "vpn ipsec phase2-interface"))]

    statics = []
    for k, v in _entries(_block(raw, "static", "router static")):
        # No `dst` shown means the default 0.0.0.0/0 — unless the route
        # targets a named address or internet service instead.
        if v.get("dst"):
            net = _mask_to_net(v.get("dst"))
        elif v.get("dstaddr") or v.get("internet-service"):
            net = None
        else:
            net = ipaddress.IPv4Network("0.0.0.0/0")
        statics.append({
            "seq": _int(k), "dst": str(net) if net else _str(v.get("dst")), "dstaddr": _str(v.get("dstaddr")),
            "gateway": _str(v.get("gateway")), "device": _str(v.get("device")),
            "sdwan_zone": _list(v.get("sdwan-zone")), "distance": _int(v.get("distance")) or 10,
            "priority": _int(v.get("priority")) or 0, "status": _str(v.get("status")) or "enable",
            "blackhole": _str(v.get("blackhole")) == "enable", "comment": _str(v.get("comment")),
        })

    settings_blk = _block(raw, "settings", "system settings")
    addresses = {}
    for n, v in _entries(_block(raw, "address", "firewall address")):
        t = _str(v.get("type")) or "ipmask"
        nets = []
        if t == "ipmask":
            net = _mask_to_net(v.get("subnet") or ["0.0.0.0", "0.0.0.0"])
            nets = [net] if net else []
        elif t == "iprange" and v.get("start-ip") and v.get("end-ip"):
            try:
                nets = list(ipaddress.summarize_address_range(
                    ipaddress.IPv4Address(_str(v["start-ip"])), ipaddress.IPv4Address(_str(v["end-ip"]))))
            except ValueError:
                nets = []
        addresses[n] = {"type": t, "nets": [str(x) for x in nets], "fqdn": _str(v.get("fqdn"))}
    groups = {n: _list(v.get("member")) for n, v in _entries(_block(raw, "addrgrp", "firewall addrgrp"))}

    shapers = [{
        "name": n, "guaranteed_kbps": _int(v.get("guaranteed-bandwidth")) or 0,
        "maximum_kbps": _int(v.get("maximum-bandwidth")) or 0, "priority": _str(v.get("priority")) or "high",
        "per_policy": _str(v.get("per-policy")),
    } for n, v in _entries(_block(raw, "shaper", "firewall shaper traffic-shaper"))]
    shaping = [{
        "id": _int(k), "name": _str(v.get("name")), "status": _str(v.get("status")) or "enable",
        "srcaddr": _list(v.get("srcaddr")), "dstaddr": _list(v.get("dstaddr")),
        "dstintf": _list(v.get("dstintf")), "service": _list(v.get("service")),
        "traffic_shaper": _str(v.get("traffic-shaper")), "traffic_shaper_reverse": _str(v.get("traffic-shaper-reverse")),
    } for k, v in _entries(_block(raw, "shaping", "firewall shaping-policy"))]

    status = fortigate.parse_status(raw.get("status", ""))
    return {
        **status,
        "sdwan_status": _str(sd.get("status")) or "disable",
        "load_balance_mode": _str(sd.get("load-balance-mode")),
        "zones": [n for n, _ in _entries(sd.get("zone"))],
        "members": members, "health_checks": health, "services": services,
        "phase1": phase1, "phase2": phase2, "static_routes": statics,
        "interfaces": ifaces, "addresses": addresses, "groups": groups,
        "shapers": shapers, "shaping_policies": shaping,
        "asymroute": _str(settings_blk.get("asymroute")) or "disable",
        "live_health": fortigate.parse_sdwan_health(raw.get("sdwan_health", "")),
        "live_services": parse_live_services(raw.get("sdwan_service", "")),
    }


def parse_live_services(raw: str) -> list[dict]:
    """`diagnose sys sdwan service` — per rule, members in the order the
    FortiGate currently prefers them:
      Service(1): Address Mode(IPV4) flags=0x200 ...
        Gen(1), TOS(0x0/0x0), Protocol(0: 1->65535), Mode(sla), ...
        Members(2):
          1: Seq_num(3 CKR-JKT), alive, sla(0x1), gid(0), cfg_order(0), ..., selected
    """
    out = []
    for block in re.split(r"\n(?=\s*Service\(\d+\))", raw or ""):
        h = re.search(r"Service\((\d+)\)", block)
        if not h:
            continue
        mode = re.search(r",\s*Mode\(([\w-]+)\)", block)   # not "Address Mode(IPV4)"
        members = [{
            "order": int(m.group(1)), "seq": int(m.group(2)), "interface": m.group(3).strip(),
            "state": m.group(4), "selected": "selected" in m.group(5),
        } for m in re.finditer(r"^\s*(\d+):\s*Seq_num\((\d+)\s+([^)]+)\),\s*(\w+)(.*)$", block, re.M)]
        out.append({"id": int(h.group(1)), "mode": mode.group(1) if mode else None, "members": members})
    return out


# ── Address helpers ────────────────────────────────────────────────────────

def _resolve(dev: dict, names: list[str], depth: int = 0) -> tuple[list, bool]:
    """Address/group names → networks. Second value False when something
    could not be resolved (FQDN, geography, unknown name)."""
    nets, known = [], True
    for n in names:
        if n in dev["addresses"]:
            a = dev["addresses"][n]
            if a["nets"]:
                nets += [ipaddress.IPv4Network(x) for x in a["nets"]]
            else:
                known = False
        elif n in dev["groups"] and depth < 5:
            sub, ok = _resolve(dev, dev["groups"][n], depth + 1)
            nets += sub
            known = known and ok
        elif n == "all":
            nets.append(ipaddress.IPv4Network("0.0.0.0/0"))
        else:
            known = False
    return nets, known


def _covers(nets: list, ip: str) -> bool:
    try:
        a = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return any(a in n for n in nets)


def _targets_ebs(dev: dict, names: list[str], ebs_ips: list[str]) -> bool:
    """Names cover an EBS address specifically — a catch-all "all" does not count."""
    nets = [n for n in _resolve(dev, names)[0] if n.prefixlen > 0]
    return any(_covers(nets, ip) for ip in ebs_ips)


def _is_tunnel(dev: dict, iface: str | None) -> bool:
    return any(p["name"] == iface for p in dev["phase1"])


def _member(dev: dict, seq: int) -> dict | None:
    return next((m for m in dev["members"] if m["seq"] == seq), None)


def _route_for(dev: dict, ip: str) -> dict | None:
    """Longest-prefix enabled static route (lowest distance on a tie)."""
    best = None
    for r in dev["static_routes"]:
        if r["status"] != "enable" or not r["dst"] or "/" not in r["dst"]:
            continue
        try:
            net = ipaddress.IPv4Network(r["dst"])
        except ValueError:
            continue
        if ipaddress.IPv4Address(ip) not in net:
            continue
        key = (net.prefixlen, -r["distance"])
        if best is None or key > best[0]:
            best = (key, r)
    return best[1] if best else None


def lan_subnets(dev: dict) -> list[str]:
    """Private subnets on non-WAN, non-tunnel interfaces — the site's LANs."""
    out = []
    for i in dev["interfaces"].values():
        if not i["ip"] or i["role"] == "wan" or i["type"] == "tunnel" or _is_tunnel(dev, i["name"]):
            continue
        net = _mask_to_net(i["ip"])
        if net and net.is_private and net.prefixlen < 32 and str(net) not in out:
            out.append(str(net))
    return out


def match_service(dev: dict, src_ip: str | None, dst_ip: str) -> dict:
    """Which SD-WAN rule a new session to dst_ip hits on this box — the
    first enabled rule in CLI order whose dst (and, when known, src) covers
    it; no rule → the implicit rule, i.e. the routing table."""
    for s in dev["services"]:
        if s["status"] != "enable" or s["internet_service"]:
            continue
        dnets, dknown = _resolve(dev, s["dst"])
        hit = _covers(dnets, dst_ip)
        if s["dst_negate"]:
            hit = dknown and not hit
        if not hit:
            continue
        note = None
        if s["src"]:
            snets, _ = _resolve(dev, s["src"])
            if src_ip:
                if _covers(snets, src_ip) == s["src_negate"]:
                    continue
            elif not any(n.prefixlen == 0 for n in snets):
                note = f"hanya bila sumber termasuk {', '.join(s['src'])}"
        if s["protocol"] not in (None, 0) or (s["start_port"] not in (None, 1) or s["end_port"] not in (None, 65535)):
            extra = f"protokol {s['protocol']} port {s['start_port']}-{s['end_port']}"
            note = f"{note}; {extra}" if note else f"hanya {extra}"
        return {"rule": s, "note": note}
    return {"rule": None, "note": None, "route": _route_for(dev, dst_ip)}


def preferred_order(dev: dict, rule: dict) -> list[dict]:
    """Members a rule would try, in order. priority-members is the rule's
    explicit order; without it FortiOS falls back to the members' cost."""
    seqs = rule["priority_members"]
    if not seqs and rule["priority_zone"]:
        seqs = [m["seq"] for m in sorted(dev["members"], key=lambda m: (m["cost"] or 0, m["seq"]))
                if m["zone"] in rule["priority_zone"]]
    return [m for m in (_member(dev, s) for s in seqs) if m]


def rule_slas(dev: dict, rule: dict) -> list[dict]:
    out = []
    for ref in rule["sla"]:
        hc = next((h for h in dev["health_checks"] if h["name"] == ref["health_check"]), None)
        sla = next((x for x in (hc or {}).get("sla", []) if x["id"] == ref["id"]), None) if hc else None
        out.append({"health_check": ref["health_check"], "id": ref["id"], "hc": hc, "sla": sla})
    return out


# ── HO ↔ Plant analysis ────────────────────────────────────────────────────

def pair_tunnels(ho: dict, plant: dict) -> list[dict]:
    """Tunnel pairs by public endpoint: HO's remote-gw is Plant's WAN IP of
    that tunnel, and/or the other way round. One tunnel each side pairs even
    without matching IPs (dialup or NAT in between)."""
    pairs, used = [], set()
    for h in ho["phase1"]:
        for p in plant["phase1"]:
            if p["name"] in used:
                continue
            if (h["remote_gw"] and h["remote_gw"] == p["local_ip"]) or (p["remote_gw"] and p["remote_gw"] == h["local_ip"]):
                pairs.append({"ho": h["name"], "plant": p["name"], "by": "IP publik"})
                used.add(p["name"])
                break
    if not pairs and len(ho["phase1"]) == 1 and len(plant["phase1"]) == 1:
        pairs.append({"ho": ho["phase1"][0]["name"], "plant": plant["phase1"][0]["name"], "by": "satu-satunya tunnel"})
    for pr in pairs:
        h = next(x for x in ho["phase1"] if x["name"] == pr["ho"])
        p = next(x for x in plant["phase1"] if x["name"] == pr["plant"])
        pr["ho_path"] = f"{h['interface']} {h['local_ip'] or ''} → {h['remote_gw'] or '?'}".strip()
        pr["plant_path"] = f"{p['interface']} {p['local_ip'] or ''} → {p['remote_gw'] or '?'}".strip()
        pr["ho_member"] = next((m["seq"] for m in ho["members"] if m["interface"] == pr["ho"]), None)
        pr["plant_member"] = next((m["seq"] for m in plant["members"] if m["interface"] == pr["plant"]), None)
    return pairs


def _flow(dev: dict, src_ip: str | None, dst_ip: str, label: str) -> dict:
    m = match_service(dev, src_ip, dst_ip)
    out = {"label": label, "src": src_ip, "dst": dst_ip, "note": m["note"]}
    if m["rule"]:
        r = m["rule"]
        order = preferred_order(dev, r)
        out.update({
            "via": "rule", "rule_id": r["id"], "rule_name": r["name"], "mode": r["mode"],
            "order": [{"seq": x["seq"], "interface": x["interface"], "tunnel": _is_tunnel(dev, x["interface"])} for x in order],
            "slas": [{"health_check": s["health_check"], "id": s["id"], **(s["sla"] or {})} for s in rule_slas(dev, r)],
        })
        live = next((x for x in dev["live_services"] if x["id"] == r["id"]), None)
        if live:
            first = next((x for x in live["members"] if x["state"] == "alive"), None)
            out["live_first_alive"] = first["interface"] if first else None
    else:
        rt = m.get("route")
        out.update({"via": "route", "route": rt,
                    "order": [{"interface": z, "tunnel": False, "zone": True} for z in (rt or {}).get("sdwan_zone", [])]
                    or ([{"interface": rt["device"], "tunnel": _is_tunnel(dev, rt["device"])}] if rt and rt.get("device") else [])})
    return out


def _chk(level, device, title, detail):
    return {"level": level, "device": device, "title": title, "detail": detail}


def _device_checks(role: str, dev: dict, ebs_ips: list[str]) -> list[dict]:
    out = []
    if dev["sdwan_status"] != "enable":
        out.append(_chk("info", role, "SD-WAN belum aktif",
                        "Routing masih statis biasa: trafik antar-site memakai route ke satu tunnel, jadi secara alami satu jalur bolak-balik — tetapi tanpa failover otomatis."))
    # `set members 0` on a health check means every member.
    covered = {s for h in dev["health_checks"] for s in h["members"]}
    for m in dev["members"]:
        if _is_tunnel(dev, m["interface"]) and 0 not in covered and m["seq"] not in covered:
            out.append(_chk("warn", role, f"Tunnel {m['interface']} tanpa health check",
                            "Member overlay ini tidak diukur oleh performance SLA mana pun, jadi SD-WAN tidak bisa tahu kapan tunnel ini buruk dan tidak akan memindahkan EBS darinya."))
    for h in dev["health_checks"]:
        hc_members = dev["members"] if 0 in h["members"] else [m for m in map(lambda s: _member(dev, s), h["members"]) if m]
        if not any(_is_tunnel(dev, m["interface"]) for m in hc_members):
            continue
        if (h["recoverytime"] or 0) < 10:
            out.append(_chk("warn", role, f"Health check {h['name']}: recoverytime {h['recoverytime']}",
                            "Runbook memakai recoverytime 10. Nilai kecil membuat jalur cepat kembali setelah pulih → risiko flapping saat link radio iForte naik-turun waktu hujan; setiap perpindahan bisa memutus sesi Forms."))
    if dev["asymroute"] == "enable":
        out.append(_chk("warn", role, "asymroute aktif",
                        "FortiGate meneruskan trafik asimetris tanpa inspeksi stateful. Ini menyembunyikan masalah jalur bolak-balik yang berbeda dan melemahkan keamanan — sebaiknya dimatikan."))
    for p in dev["phase1"]:
        if (p["dpd"] or "disable") == "disable":
            out.append(_chk("warn", role, f"Tunnel {p['name']}: DPD mati",
                            "Tanpa Dead Peer Detection tunnel yang mati tidak segera terdeteksi; failover menunggu SA kedaluwarsa."))
    for sp in dev["shaping_policies"]:
        if sp["status"] != "enable" or not sp["traffic_shaper"] or sp["traffic_shaper_reverse"]:
            continue
        if _targets_ebs(dev, sp["srcaddr"] + sp["dstaddr"], ebs_ips):
            out.append(_chk("warn", role, f"Shaping policy #{sp['id']} tanpa traffic-shaper-reverse",
                            "Trafik EBS didominasi arah server → user. Tanpa shaper reverse, prioritas tidak berlaku di arah yang paling padat."))
    return out


def analyze(ho: dict | None, plant: dict | None, ebs_ips: list[str]) -> dict:
    checks, pairs, flows = [], [], []
    if ho:
        checks += _device_checks("HO", ho, ebs_ips)
    if plant:
        checks += _device_checks("Plant", plant, ebs_ips)
    if not (ho and plant):
        checks.append(_chk("info", "HO↔Plant", "Perbandingan dua sisi belum bisa dibuat",
                           "Baca konfigurasi kedua FortiGate untuk memeriksa apakah EBS memakai tunnel yang sama di kedua arah."))
        return {"checks": checks, "pairs": pairs, "flows": flows, "ho_lans": [], "ebs_ips": ebs_ips}

    pairs = pair_tunnels(ho, plant)
    by_ho = {p["ho"]: p for p in pairs}
    by_plant = {p["plant"]: p for p in pairs}
    for p in ho["phase1"]:
        if p["name"] not in by_ho:
            checks.append(_chk("warn", "HO", f"Tunnel {p['name']} tidak punya pasangan di Plant",
                               f"remote-gw {p['remote_gw']} tidak cocok dengan IP WAN tunnel mana pun di FortiGate Plant."))
    for p in plant["phase1"]:
        if p["name"] not in by_plant:
            checks.append(_chk("warn", "Plant", f"Tunnel {p['name']} tidak punya pasangan di HO",
                               f"remote-gw {p['remote_gw']} tidak cocok dengan IP WAN tunnel mana pun di FortiGate HO."))

    ho_lans = lan_subnets(ho)
    ho_probe = next((str(next(ipaddress.IPv4Network(n).hosts())) for n in ho_lans), None)
    ebs = ebs_ips[0] if ebs_ips else None
    if ebs:
        f_ho = _flow(ho, None, ebs, "User HO membuka EBS (FGT HO memilih tunnel)")
        flows.append(f_ho)
        f_pl = None
        if ho_probe:
            f_pl = _flow(plant, ebs, ho_probe, "Server EBS membuka koneksi ke HO (FGT Plant memilih tunnel)")
            flows.append(f_pl)

        for role, f in (("HO", f_ho), ("Plant", f_pl)):
            if not f or f["via"] != "rule":
                continue
            if f["mode"] == "load-balance":
                checks.append(_chk("crit", role, f"Trafik EBS kena aturan load-balance #{f['rule_id']} {f['rule_name'] or ''}",
                                   "Sesi EBS disebar ke beberapa jalur. Untuk Oracle Forms pakai mode sla (atau priority): satu jalur utama, jalur lain cadangan."))
            if f["mode"] == "sla" and not f["slas"]:
                checks.append(_chk("warn", role, f"Aturan EBS #{f['rule_id']} mode sla tanpa SLA",
                                   "Mode sla tanpa referensi health-check/SLA tidak punya dasar untuk memilih atau memindahkan jalur."))

        def as_pairs(order, idx):
            """Member order → [(HO tunnel, Plant tunnel)] so both sides compare."""
            return [(idx[o["interface"]]["ho"], idx[o["interface"]]["plant"]) for o in order if o.get("interface") in idx]

        if f_ho["via"] == "rule" and f_pl and f_pl["via"] == "rule":
            o_ho, o_pl = as_pairs(f_ho["order"], by_ho), as_pairs(f_pl["order"], by_plant)
            if o_ho and o_pl and o_ho != o_pl:
                checks.append(_chk("crit", "HO↔Plant", "Urutan tunnel EBS berbeda di HO dan Plant",
                                   f"HO memilih {' → '.join(a for a, _ in o_ho)}, Plant memilih {' → '.join(b for _, b in o_pl)} (dipasangkan per tunnel). "
                                   "Koneksi yang dibuka dari dua sisi akan lewat tunnel berbeda — samakan priority-members."))
            elif o_ho and o_pl:
                checks.append(_chk("ok", "HO↔Plant", "Urutan tunnel EBS sama di kedua sisi",
                                   f"Pasangan utama: {o_ho[0][0]} (HO) ↔ {o_ho[0][1]} (Plant)."))
            s_ho = [(s.get("latency_ms"), s.get("jitter_ms"), s.get("loss_pct"), tuple(s.get("link_cost_factor") or [])) for s in f_ho["slas"]]
            s_pl = [(s.get("latency_ms"), s.get("jitter_ms"), s.get("loss_pct"), tuple(s.get("link_cost_factor") or [])) for s in f_pl["slas"]]
            if s_ho and s_pl and s_ho[0] != s_pl[0]:
                checks.append(_chk("warn", "HO↔Plant", "Ambang SLA EBS berbeda di HO dan Plant",
                                   f"HO latency/jitter/loss {s_ho[0][:3]}, Plant {s_pl[0][:3]}. Satu sisi bisa pindah tunnel sementara sisi lain tidak."))
            if f_ho["mode"] != f_pl["mode"]:
                checks.append(_chk("warn", "HO↔Plant", "Mode aturan EBS berbeda",
                                   f"HO mode {f_ho['mode']}, Plant mode {f_pl['mode']}."))
        elif f_pl:
            # At least one side routes statically: compare the first choice.
            t_ho = next((o["interface"] for o in f_ho["order"] if o.get("interface") in by_ho), None)
            t_pl = next((o["interface"] for o in f_pl["order"] if o.get("interface") in by_plant), None)
            if t_ho and t_pl and by_ho[t_ho]["plant"] == t_pl:
                checks.append(_chk("ok", "HO↔Plant", "EBS memakai satu jalur bolak-balik",
                                   f"HO → Plant lewat {t_ho}, Plant → HO lewat {t_pl} — pasangan tunnel yang sama."))
            elif t_ho and t_pl:
                checks.append(_chk("crit", "HO↔Plant", "Jalur pergi dan pulang EBS berbeda",
                                   f"HO memakai {t_ho} (pasangannya {by_ho[t_ho]['plant']}), tetapi Plant mengarah ke HO lewat {t_pl}."))
        if ho["sdwan_status"] == "enable" and f_ho["via"] == "route":
            checks.append(_chk("warn", "HO", "Tidak ada aturan SD-WAN untuk EBS di HO",
                               "Sesi EBS dibuka dari laptop HO, jadi FGT HO-lah yang memilih tunnel. Tanpa aturan sla di HO, EBS ikut routing table dan tidak dipindahkan saat tunnel buruk. Runbook Fase 6 baru menulis aturan sisi Plant — tambahkan cerminnya di HO."))
        if f_ho["via"] == "rule" and f_pl and f_pl["via"] == "route" and plant["sdwan_status"] == "enable":
            checks.append(_chk("info", "Plant", "Plant tidak punya aturan untuk koneksi EBS → HO",
                               "Tidak masalah untuk sesi user (balasan mengikuti sesi), tetapi koneksi yang dibuka server EBS ke HO akan mengikuti routing table, bukan urutan tunnel HO."))
        if f_ho["via"] == "route" and f_ho.get("route") is None:
            checks.append(_chk("crit", "HO", f"Tidak ada route ke EBS {ebs}",
                               "Tidak ada static route yang mencakup alamat EBS di FGT HO (bisa juga lewat BGP/OSPF — cek get router info routing-table details)."))

    for h_hc in ho["health_checks"]:
        p_hc = next((x for x in plant["health_checks"] if x["name"] == h_hc["name"]), None)
        if p_hc and (h_hc["interval_ms"], h_hc["failtime"], h_hc["recoverytime"]) != (p_hc["interval_ms"], p_hc["failtime"], p_hc["recoverytime"]):
            checks.append(_chk("warn", "HO↔Plant", f"Timer health check {h_hc['name']} berbeda",
                               f"HO interval/failtime/recovery {h_hc['interval_ms']}/{h_hc['failtime']}/{h_hc['recoverytime']}, "
                               f"Plant {p_hc['interval_ms']}/{p_hc['failtime']}/{p_hc['recoverytime']}. Kedua sisi bereaksi pada waktu berbeda."))

    rank = {"crit": 0, "warn": 1, "info": 2, "ok": 3}
    checks.sort(key=lambda c: rank.get(c["level"], 9))
    return {"checks": checks, "pairs": pairs, "flows": flows, "ho_lans": ho_lans, "ebs_ips": ebs_ips}


# ── Capture ────────────────────────────────────────────────────────────────

def capture(server_id: int) -> dict:
    """{ok, name, summary, raw, error} — never raises; raw is redacted."""
    srv = store.get_server(server_id, with_secret=True)
    if srv is None:
        return {"ok": False, "name": f"server #{server_id}", "summary": None, "raw": None,
                "error": "Server tidak ditemukan di Server Control"}
    if srv.get("problem"):
        return {"ok": False, "name": srv["name"], "summary": None, "raw": None, "error": srv["problem"]}
    try:
        raw = {k: redact(v) for k, v in fortigate._run_all(srv, COMMANDS).items()}
    except Exception as e:
        return {"ok": False, "name": srv["name"], "summary": None, "raw": None, "error": f"SSH gagal: {e}"}
    try:
        summary = {**normalize(raw), "address": srv["ip"]}
    except Exception as e:
        return {"ok": False, "name": srv["name"], "summary": None, "raw": raw,
                "error": f"Gagal membaca output konfigurasi: {e} — lihat output mentah"}
    return {"ok": True, "name": srv["name"], "summary": summary, "raw": raw, "error": None}
