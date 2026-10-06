"""
Server-side probes. Both are blocking and run from plain `def` routes or the
scheduler thread.

  tcp_probe  — N sequential TCP connects; each handshake is one RTT, failed
               connects count as loss. Jitter is the mean absolute
               difference between consecutive RTTs (RFC 3550 style, without
               the smoothing) — the same definition the agent and the
               browser test use, so the three numbers are comparable.
  http_probe — time to first byte of a GET, i.e. network RTT plus however
               long the EBS web tier takes to start answering. A healthy
               TCP probe with a slow TTFB points at the app tier, not the
               network (Case C).
"""
import socket
import statistics
import time

import httpx


def summarize(rtts: list[float], attempts: int) -> dict:
    ok = len(rtts)
    out = {
        "samples": attempts, "ok_count": ok,
        "loss_pct": round((attempts - ok) * 100.0 / attempts, 1) if attempts else None,
        "rtt_min": None, "rtt_avg": None, "rtt_max": None, "jitter_ms": None,
    }
    if rtts:
        out["rtt_min"] = round(min(rtts), 1)
        out["rtt_avg"] = round(statistics.fmean(rtts), 1)
        out["rtt_max"] = round(max(rtts), 1)
        if len(rtts) > 1:
            out["jitter_ms"] = round(statistics.fmean(abs(a - b) for a, b in zip(rtts, rtts[1:])), 1)
        else:
            out["jitter_ms"] = 0.0
    return out


def tcp_probe(host: str, port: int, samples: int = 5, timeout: float = 3.0, gap: float = 0.2) -> dict:
    rtts, last_error = [], None
    for i in range(samples):
        start = time.perf_counter()
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                rtts.append((time.perf_counter() - start) * 1000)
        except (socket.timeout, TimeoutError):
            last_error = f"Timeout setelah {timeout}s"
        except OSError as e:
            last_error = str(e)
        if i < samples - 1:
            time.sleep(gap)
    out = summarize(rtts, samples)
    out["error"] = _error_text(rtts, samples, last_error)
    out["http_status"] = None
    return out


def _error_text(rtts: list, samples: int, last_error: str | None) -> str | None:
    if not last_error:
        return None
    if not rtts:
        return last_error
    return f"{samples - len(rtts)}/{samples} gagal — {last_error}"


def http_probe(url: str, samples: int = 3, timeout: float = 15.0) -> dict:
    """TTFB per sample. Certificate errors are ignored on purpose: internal
    EBS web tiers commonly run a self-signed cert, and what's measured here
    is speed, not trust."""
    rtts, status, last_error = [], None, None
    with httpx.Client(verify=False, timeout=timeout, follow_redirects=False) as client:
        for i in range(samples):
            start = time.perf_counter()
            try:
                with client.stream("GET", url, headers={"Cache-Control": "no-cache"}) as r:
                    rtts.append((time.perf_counter() - start) * 1000)
                    status = r.status_code
            except httpx.TimeoutException:
                last_error = f"Timeout setelah {timeout}s"
            except Exception as e:
                last_error = str(e)
            if i < samples - 1:
                time.sleep(0.3)
    out = summarize(rtts, samples)
    out["http_status"] = status
    out["error"] = _error_text(rtts, samples, last_error)
    if status and status >= 500:
        out["error"] = f"HTTP {status}"
    return out


def run_target(target, samples: int) -> dict:
    if target.check_type == "http":
        if not target.url:
            return {"skipped": True, "error": "URL belum diisi"}
        return http_probe(target.url, samples=max(1, min(samples, 5)))
    if not target.host or not target.port:
        return {"skipped": True, "error": "Host/port belum diisi"}
    return tcp_probe(target.host, target.port, samples=samples)
