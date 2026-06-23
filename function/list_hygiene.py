"""
list_hygiene.py — Tier 1 Zero-Risk Verification Pipeline
Sentinel Jesko / Metro integrated list hygiene stack.
Zero SMTP handshake — DNS only, zero IP risk.
"""
import argparse
import csv
import dataclasses
import dns.name
import dns.resolver
import hashlib
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json as _json

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

SCRIPT_DIR  = Path(__file__).resolve().parent          # .../Sentinel Jesko/function
PROJECT_ROOT = SCRIPT_DIR.parent                       # .../Sentinel Jesko
DEFAULT_INPUT  = PROJECT_ROOT / "recipients.txt"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "verified_recipients.csv"
DB_PATH        = PROJECT_ROOT / "logs" / "hygiene_cache.db"

# dns.resolver.Resolver is NOT thread-safe for concurrent resolve() calls.
# Use thread-local storage so each worker thread owns its own resolver instance.
_thr_local = threading.local()

def _resolver() -> dns.resolver.Resolver:
    if not hasattr(_thr_local, "resolver"):
        r = dns.resolver.Resolver(configure=False)
        r.nameservers = ["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222"]
        r.lifetime = 5.0
        r.timeout  = 3.0
        _thr_local.resolver = r
    return _thr_local.resolver

# Serialize SQLite writes — the connection is shared across threads.
_db_write_lock = threading.Lock()

ROLE_PREFIXES: Set[str] = {
    "info", "support", "admin", "sales", "help", "contact", "noreply",
    "no-reply", "webmaster", "abuse", "postmaster", "marketing", "hello",
    "enquiries", "legal", "hr", "jobs", "press", "media", "feedback",
    "security", "operations", "billing", "accounts", "service", "customers",
    "salesforce", "marketo", "pardot", "eloqua", "hubspot", "mailer-daemon",
    "mailman", "listserv", "majordomo", "root", "administrator",
    "www", "ftp", "demo", "test", "spam", "nobody",
}

KNOWN_PROVIDERS: List[str] = [
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in",
    "hotmail.com", "hotmail.co.uk",
    "outlook.com", "outlook.co.uk",
    "live.co.uk", "live.com", "msn.com", "office365.com",
    "aol.com",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me",
    "zoho.com",
    "yandex.com", "yandex.ru",
    "mail.com", "gmx.com", "gmx.net",
    "fastmail.com", "tutanota.com", "qq.com",
]

COMMON_TLDS: Set[str] = {
    "com","net","org","edu","gov","mil","io","co","uk","us","ca",
    "de","fr","au","in","br","jp","cn","ru","it","es","nl","se",
    "no","fi","dk","pl","cz","at","ch","be","pt","ie","nz","sg",
    "hk","kr","mx","za","ar","cl","pe","ec","uy",
}

DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com","trashmail.com","tempmail.com","guerrillamail.com",
    "guerrillamailblock.com","sharklasers.com","grr.la","dispostable.com",
    "yopmail.com","yopmail.fr","yopmail.net","jetable.org",
    "mailforspam.com","safetymail.info","filzmail.com","tempail.com",
    "discard.email","discardmail.com","spamgourmet.com",
    "mailcatch.com","zippymail.info","meltmail.com","tempinbox.com",
    "maildrop.cc","maildrop.io","getairmail.com","throwaway.email",
    "10minutemail.com","10minutemail.net","10minutemail.org",
    "20minutemail.com","30minutemail.com","temp-mail.org","temp-mail.io",
    "fakeinbox.com","fake-email.com","fakemail.com","mailsac.com",
    "inboxkitten.com","emailondeck.com","emailtemp.info",
    "tempmail.ninja","tempmail.plus","tmail.ws","tmail.gg","tmails.net",
    "tmpmail.net","tmpmail.org","tmpmail.io","tmpbox.net",
}

MX_PROVIDER_MAP = {
    "outlook.com":"Office365","hotmail.com":"Office365",
    "live.com":"Office365","office365.com":"Office365",
    "google.com":"Google","googlemail.com":"Google",
    "yahoodns.net":"Yahoo","yahoo.com":"Yahoo",
    "secureserver.net":"GoDaddy",
    "aol.com":"AOL","icloud.com":"Apple","me.com":"Apple","mac.com":"Apple",
    "zoho.com":"Zoho","yandex.com":"Yandex","yandex.ru":"Yandex",
    "protonmail.com":"Proton","proton.me":"Proton",
    "fastmail.com":"Fastmail","mail.com":"Mail.com",
}

DMARC_POLICY_WEIGHT = {"reject":0.15,"quarantine":0.05,"none":0.0,"":-0.05}

# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    email: str = ""
    original_input: str = ""
    service: str = "Unknown"
    status: str = ""            # deliverable | undeliverable | risky | ...
    mx_ok: bool = False
    mx_records: str = ""
    has_spf: str = ""
    has_dmarc: str = ""
    dmarc_policy: str = ""
    has_dkim: str = ""
    is_role: bool = False
    is_disposable: bool = False
    is_typo: bool = False
    typo_suggestion: str = ""
    catch_all: bool = False
    score: float = 0.0
    verdict: str = "unknown"
    raw_error: str = ""

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(str(DB_PATH)), exist_ok=True)
    # check_same_thread=False + serialized writes allow safe cross-thread
    # access to the shared cache connection used by the thread pool.
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads, exclusive writes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dns_cache (
            domain       TEXT,
            query_type   TEXT,
            result       TEXT,
            fetched_at   REAL,
            PRIMARY KEY (domain, query_type)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bounce_history (
            email      TEXT PRIMARY KEY,
            verdict    TEXT,
            updated_at REAL
        )""")
    conn.commit()
    return conn

def _cache_get(conn: sqlite3.Connection, domain: str, qtype: str, ttl_seconds: int) -> Optional[list]:
    now = time.time()
    row = conn.execute(
        "SELECT result, fetched_at FROM dns_cache WHERE domain=? AND query_type=?",
        (domain.lower(), qtype.upper())
    ).fetchone()
    if row and (now - row[1]) < ttl_seconds:
        try:
            return _json.loads(row[0])
        except Exception:
            return None
    return None

def _cache_set(conn: sqlite3.Connection, domain: str, qtype: str, value: list):
    conn.execute(
        "INSERT OR REPLACE INTO dns_cache (domain, query_type, result, fetched_at) VALUES (?,?,?,?)",
        (domain.lower(), qtype.upper(), _json.dumps(value), time.time())
    )
    conn.commit()

def _bounce_get(conn: sqlite3.Connection, email: str) -> Optional[str]:
    row = conn.execute("SELECT verdict FROM bounce_history WHERE email=?", (email.lower(),)).fetchone()
    return row[0] if row else None

def _bounce_set(conn: sqlite3.Connection, email: str, verdict: str):
    with _db_write_lock:
        conn.execute(
            "INSERT OR REPLACE INTO bounce_history (email, verdict, updated_at) VALUES (?,?,?)",
            (email.lower(), verdict, time.time())
        )
        conn.commit()

# ---------------------------------------------------------------------------
# Syntax & normalization
# ---------------------------------------------------------------------------

def normalize_email(raw: str) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip().lower()
    raw = raw.strip('<> "\'\t\r\n;')
    # Structural check — require exactly one @ after stripping
    if "@" not in raw:
        return None
    local, domain = raw.rsplit("@", 1)
    # Basic shape check
    if not re.match(r"^[a-z0-9._%+\-]+$", local) or not re.match(r"^[a-z0-9.\-]+\.[a-z]{2,}$", domain, re.I):
        return None
    local = local.split("+")[0]
    return f"{local}@{domain}"

def is_role(local: str) -> bool:
    return local.split("+")[0].lower() in ROLE_PREFIXES

def is_disposable(domain: str) -> bool:
    return domain.lower() in DISPOSABLE_DOMAINS

# ---------------------------------------------------------------------------
# Typosquatting (static dictionary — no external deps)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    curr = [0] * (len(b) + 1)
    for i, ca in enumerate(a, 1):
        curr[0] = i
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + (0 if ca == cb else 1))
        prev, curr = curr, prev
    return prev[len(b)]

def detect_typo(domain: str) -> Tuple[bool, str]:
    domain = domain.lower().rstrip(".")
    labels = domain.split(".")
    if len(labels) < 2:
        return False, ""
    base, tld = labels[0], labels[-1]
    if tld not in COMMON_TLDS:
        return False, ""
    # Only compare against providers sharing the same TLD.
    # Use levenshtein on the base (SLD) with length-normalized threshold
    # to avoid false positives like "gmail.com" matching "mail.com".
    for prov in KNOWN_PROVIDERS:
        prov_labels = prov.split(".")
        if len(prov_labels) < 2:
            continue
        prov_base, prov_tld = prov_labels[0], prov_labels[-1]
        if prov_tld != tld:
            continue                    # different TLD, not a look-alike
        dist = _levenshtein(base, prov_base)
        if dist == 0:
            continue                    # exact match, not a typo
        max_len = max(len(base), len(prov_base), 1)
        ratio  = dist / max_len
        # Real typos: ≤ 2 edits AND ≤ 33 % altered
        # Skip substring matches (e.g. "gmail" contains "mail") — not a real typo.
        if dist <= 2 and ratio <= 0.33 and base not in prov_base and prov_base not in base:
            return True, prov
    return False, ""
# DNS helpers (with cache)
# ---------------------------------------------------------------------------

def _query(conn: sqlite3.Connection, domain: str, qtype: str, ttl: int) -> Optional[list]:
    cached = _cache_get(conn, domain, qtype, ttl)
    if cached is not None:
        return cached
    try:
        answers = _resolver().resolve(domain, qtype)
        vals = [str(r).rstrip(".") for r in answers]
        # Serialize cache writes — connection is shared across threads
        with _db_write_lock:
            _cache_set(conn, domain, qtype, vals)
        return vals
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        with _db_write_lock:
            _cache_set(conn, domain, qtype, [])
        return []
    except Exception:
        # timeout / SERVFAIL — keep ambiguous, don't cache false-negative
        return None

def classify_service(mx_records: List[str]) -> str:
    for mx in mx_records:
        low = mx.lower()
        for suffix, name in MX_PROVIDER_MAP.items():
            if low.endswith(suffix):
                return name
    return "Other"

# ---------------------------------------------------------------------------
# Tier-1 verification
# ---------------------------------------------------------------------------

def verify_email(conn: sqlite3.Connection, raw_email: str) -> VerificationResult:
    original = raw_email.strip()
    normalized = normalize_email(original)
    if not normalized:
        return VerificationResult(
            email="", original_input=original, mx_ok=False,
            verdict="invalid_syntax", raw_error="syntax_failed"
        )

    local, domain = normalized.rsplit("@", 1)
    r = VerificationResult(email=normalized, original_input=original)

    # --- hard-fail first (no DNS needed) ---
    r.is_role       = is_role(local)
    r.is_disposable  = is_disposable(domain)
    r.is_typo, r.typo_suggestion = detect_typo(domain)

    if r.is_disposable:
        r.mx_ok = False
        r.service = "Disposable"
        r.verdict = "disposable"
        r.score   = 0.0
        return r

    # --- MX ---
    mx_records = _query(conn, domain, "MX", 1800)
    if mx_records is None:
        r.mx_ok = False
        r.raw_error = "dns_timeout"
        r.verdict   = "unverified"
        r.score     = 0.0
        return r
    r.mx_ok      = bool(mx_records)
    r.mx_records = ";".join(mx_records) if mx_records else ""
    r.service    = classify_service(mx_records) if r.mx_ok else "Unknown"

    if not r.mx_ok:
        r.verdict = "undeliverable"
        r.score   = 0.0
        return r

    # --- DNS auth (SPF / DMARC / DKIM) ---
    spf = _query(conn, domain, "TXT", 3600)
    r.has_spf = "present" if spf and any("v=spf1" in (v or "").lower() for v in spf) else "absent"

    dmarc_answers = _query(conn, f"_dmarc.{domain}", "TXT", 3600)
    if dmarc_answers:
        policy = "none"
        for v in dmarc_answers:
            m = re.search(r"p\s*=\s*(\w+)", v, re.I)
            if m:
                policy = m.group(1).lower()
                break
        r.has_dmarc    = "present"
        r.dmarc_policy = policy
    else:
        r.has_dmarc    = "absent"
        r.dmarc_policy = ""

    dkim_hits = 0
    for selector in ("default", "selector1", "selector2", "google", "k1", "s1"):
        dkim_ans = _query(conn, f"{selector}._domainkey.{domain}", "TXT", 3600)
        if dkim_ans and any("v=dkim1" in (v or "").lower() for v in dkim_ans):
            dkim_hits += 1
    r.has_dkim = "present" if dkim_hits > 0 else "absent"

    # --- score + verdict ---
    return _finalize(r)

# ---------------------------------------------------------------------------
# Scoring & verdict
# ---------------------------------------------------------------------------

def _finalize(r: VerificationResult) -> VerificationResult:
    s = 0.10                        # base existence bonus
    if r.mx_ok:       s += 0.20
    if r.has_spf == "present":    s += 0.10
    if r.has_dmarc in ("reject","quarantine"): s += 0.15
    if r.has_dmarc == "reject":   s += 0.05
    if r.has_dkim == "present":   s += 0.10
    if r.catch_all:   s -= 0.40
    if r.is_role:     s -= 0.50
    if r.is_disposable: s -= 1.00
    if r.is_typo:     s -= 0.60
    if r.mx_ok and r.has_spf == "absent": s -= 0.10
    r.score = round(max(0.0, min(1.0, s)), 2)

    if r.is_disposable:
        r.verdict = "disposable"
    elif r.is_typo:
        r.verdict = "typo_risky"
    elif r.is_role:
        r.verdict = "role"
    elif not r.mx_ok:
        r.verdict = "undeliverable"
    elif r.score <= 0.25:
        r.verdict = "undeliverable"
    elif r.score <= 0.50:
        r.verdict = "risky"
    elif r.catch_all:
        r.verdict = "catch_all_risky"
    else:
        r.verdict = "deliverable"
    return r

# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def process_batch(emails: List[str], concurrency: int = 25,
                  conn: Optional[sqlite3.Connection] = None) -> List[VerificationResult]:
    own_conn = False
    if conn is None:
        conn = _init_db()
        own_conn = True

    results: List[VerificationResult] = []
    seen: Set[str] = set()

    def _worker(email: str) -> VerificationResult:
        return verify_email(conn, email)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_worker, e): e for e in emails}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                res = fut.result()
            except Exception as exc:
                res = VerificationResult(
                    email=normalize_email(futures[fut]) or futures[fut].strip(),
                    original_input=futures[fut], mx_ok=False,
                    service="Error", verdict="unverified", score=0.0,
                    raw_error=f"worker_exception:{exc}"
                )
            if res.email and res.email not in seen:
                seen.add(res.email)
                results.append(res)

    if own_conn:
        conn.close()
    return results

# ---------------------------------------------------------------------------
# Bounce-history ingestion from Sentinel Jesko logs
# ---------------------------------------------------------------------------

def ingest_bounce_history(
    results: List[VerificationResult],
    send_report: Path = PROJECT_ROOT / "logs" / "send_report.csv",
    suppression: Path = PROJECT_ROOT / "logs" / "suppression_list.txt",
) -> List[VerificationResult]:
    known_bad: Dict[str, str] = {}
    if send_report.exists():
        with open(send_report, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("result") == "failure":
                    addr = row.get("recipient", "").lower()
                    if addr:
                        known_bad[addr] = "hard_bounce"
    if suppression.exists():
        with open(suppression, "r", encoding="utf-8") as f:
            for line in f:
                addr = line.strip().lower()
                if addr:
                    known_bad[addr] = "suppressed"

    if not known_bad:
        return results

    conn = _init_db()
    for addr, v in known_bad.items():
        _bounce_set(conn, addr, v)
    conn.close()

    lookup = {r.email.lower(): r for r in results}
    for addr, v in known_bad.items():
        if addr in lookup:
            lookup[addr].verdict   = v
            lookup[addr].score     = 0.0
            lookup[addr].raw_error = "historical_suppression"
    return list(lookup.values())

# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "email","original_input","service","status",
    "mx_ok","mx_records",
    "has_spf","has_dmarc","dmarc_policy","has_dkim",
    "is_role","is_disposable","is_typo","typo_suggestion",
    "catch_all","score","verdict","raw_error",
]

VERDICT_KEEP = {"deliverable", "risky", "catch_all_risky"}

def write_csv(results: List[VerificationResult], output_path: Path,
              keep_verdicts: Set[str] = None) -> Tuple[List[VerificationResult], int]:
    if keep_verdicts is None:
        keep_verdicts = VERDICT_KEEP
    kept  = [r for r in results if r.verdict in keep_verdicts]
    dropped = len(results) - len(kept)
    kept.sort(key=lambda r: (-r.score, r.email))
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in kept:
            writer.writerow(dataclasses.asdict(r))
    return kept, dropped

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def print_summary(results: List[VerificationResult], kept: int, dropped: int):
    from collections import Counter
    counts = Counter(r.verdict for r in results)
    print(f"\n{'='*50}")
    print(f"Processed : {len(results)}")
    print(f"Kept      : {kept}")
    print(f"Dropped   : {dropped}")
    print(f"{'-'*50}")
    for verdict, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {verdict:<20}: {count}")
    print(f"{'='*50}\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Sentinel Jesko — List Hygiene Pipeline (Tier 1 DNS-only, zero IP risk)"
    )
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--concurrency", type=int, default=25)
    ap.add_argument("--no-history", action="store_true",
                    help="Skip Sentinel Jesko bounce-history ingestion")
    ap.add_argument("--keep-all", action="store_true",
                    help="Keep every verdict in the output CSV")
    ap.add_argument("--cache-ttl", type=int, default=86400,
                    help="DNS cache TTL seconds (default: 86400 = 24h)")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"FATAL: Input file not found: {args.input}")
        sys.exit(1)

    raw = [ln.strip() for ln in args.input.read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.strip().startswith("#")]
    if not raw:
        print("FATAL: No emails in input file.")
        sys.exit(1)

    print(f"--- Sentinel Jesko List Hygiene ---")
    print(f"Input  : {args.input}  ({len(raw)} lines)")
    print(f"Output : {args.output}")
    print(f"Workers: {args.concurrency}")

    conn = _init_db()
    results = process_batch(raw, concurrency=args.concurrency, conn=conn)
    if not args.no_history:
        results = ingest_bounce_history(results)
    kept, dropped = write_csv(results, args.output)
    print_summary(results, len(kept), dropped)
    print(f"CSV written to: {args.output}")

if __name__ == "__main__":
    main()
