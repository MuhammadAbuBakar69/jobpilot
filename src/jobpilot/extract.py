"""Structured extraction of job postings from free text.

Two paths:
  * ``parse_heuristic``  - no network, no key, deterministic. Always available.
  * ``parse_with_llm``   - optional; uses an LLM when a key is configured and
    falls back to the heuristic parser on any failure.

The heuristic path is the default so the project works offline and in CI.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

MONEY = re.compile(
    r"(?P<cur>PKR|USD|EUR|GBP|\$|€|£|Rs\.?)\s?"
    r"(?P<low>\d[\d,\.]*)\s?(?:k|K)?"
    r"(?:\s?(?:-|–|to)\s?(?P<cur2>PKR|USD|EUR|GBP|\$|€|£|Rs\.?)?\s?"
    r"(?P<high>\d[\d,\.]*)\s?(?:k|K)?)?"
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL = re.compile(r"https?://[^\s)>\"']+")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y", "%d %b %Y", "%B %d, %Y")

ROLE_WORDS = (
    "engineer", "developer", "designer", "manager", "analyst", "scientist",
    "architect", "intern", "consultant", "specialist", "lead", "administrator",
)
SENIORITY = (
    "intern", "junior", "mid", "senior", "staff", "principal", "lead", "head",
)
REMOTE_WORDS = ("remote", "hybrid", "on-site", "onsite", "in office", "work from home")
COMPANY_HINTS = ("at ", "company:", "organization:", "organisation:", "@ ")


@dataclass
class JobPosting:
    """One application record, normalised from whatever text came in."""

    company: str = ""
    role: str = ""
    location: str = ""
    seniority: str = ""
    work_mode: str = ""
    salary_low: int | None = None
    salary_high: int | None = None
    currency: str = ""
    deadline: str | None = None
    url: str = ""
    contact: str = ""
    skills: list[str] = field(default_factory=list)
    source: str = "manual"
    notes: str = ""
    status: str = "applied"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SKILL_VOCAB = {
    "python", "javascript", "typescript", "react", "next.js", "node.js", "express",
    "mongodb", "postgres", "mysql", "sqlite", "supabase", "firebase", "tailwind",
    "docker", "kubernetes", "aws", "gcp", "azure", "git", "linux", "fastapi",
    "django", "flask", "langchain", "openai", "llm", "rag", "n8n", "figma",
    "three.js", "graphql", "redis", "celery", "pytest", "jest", "ci/cd",
}


def _clean_money(raw: str) -> int | None:
    """'1,20,000' -> 120000, '80k' -> 80000, 'garbage' -> None."""
    if not raw:
        return None
    try:
        number = float(raw.replace(",", ""))
    except ValueError:
        return None
    if number < 1000:  # shorthand such as "80k"
        number *= 1000
    return int(number)


def _find_salary(text: str) -> tuple[int | None, int | None, str]:
    for match in MONEY.finditer(text):
        low = _clean_money(match.group("low"))
        high = _clean_money(match.group("high")) if match.group("high") else None
        if low is None or low < 1000:
            continue
        return low, high, (match.group("cur") or "").replace(".", "")
    return None, None, ""


def _find_deadline(text: str, today: date | None = None) -> str | None:
    today = today or date.today()
    date_pattern = (
        r"\b(\d{4}-\d{2}-\d{2}"          # 2026-12-15
        r"|\d{1,2}[/-]\d{1,2}[/-]\d{4}"   # 15/12/2026
        r"|[A-Z][a-z]{2,8} \d{1,2}, \d{4}"  # Dec 15, 2026
        r"|\d{1,2} [A-Z][a-z]{2,8} \d{4})\b"  # 15 Dec 2026
    )
    for token in re.findall(date_pattern, text):
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(token, fmt).date()
            except ValueError:
                continue
            if parsed >= today - timedelta(days=1):
                return parsed.isoformat()
    if re.search(r"\b(asap|immediately|rolling)\b", text, re.I):
        return None
    return None


def _line_with(text: str, hints: tuple[str, ...]) -> str:
    for line in text.splitlines():
        low = line.lower()
        if any(h in low for h in hints) and len(line.strip()) < 120:
            return line.strip()
    return ""


def parse_heuristic(text: str, today: date | None = None) -> JobPosting:
    """Deterministic, offline extraction. This is the fallback and the default."""
    text = (text or "").strip()
    posting = JobPosting()
    if not text:
        return posting

    lines = [line.strip(" -*•\t") for line in text.splitlines() if line.strip()]

    # role: prefer a short line containing a role word
    for line in lines[:8]:
        low = line.lower()
        if len(line) <= 90 and any(word in low for word in ROLE_WORDS):
            posting.role = line
            break

    # company: "at X", "Company: X", or the first short non-role line
    for line in lines[:8]:
        low = line.lower()
        for hint in COMPANY_HINTS:
            if hint in low:
                candidate = line[low.index(hint) + len(hint):].strip(" ,.-|")
                if 1 < len(candidate) <= 60:
                    posting.company = candidate
                    break
        if posting.company:
            break

    # location / work mode
    loc_line = _line_with(text, ("location", "based in", "city", "remote", "hybrid"))
    posting.location = re.sub(r"(?i)^(location|based in)\s*[:\-]\s*", "", loc_line)[:80]
    for word in REMOTE_WORDS:
        if word in text.lower():
            posting.work_mode = "remote" if "remote" in word else word
            break

    # seniority
    for word in SENIORITY:
        if re.search(rf"\b{word}\b", text, re.I):
            posting.seniority = word
            break

    posting.salary_low, posting.salary_high, posting.currency = _find_salary(text)
    posting.deadline = _find_deadline(text, today)

    urls = URL.findall(text)
    posting.url = urls[0] if urls else ""
    emails = EMAIL.findall(text)
    posting.contact = emails[0] if emails else ""

    low = text.lower()
    posting.skills = sorted({skill for skill in SKILL_VOCAB if skill in low})
    return posting


def _as_int(value: Any, fallback: int | None) -> int | None:
    """LLMs return numbers as strings or floats; keep only real integers."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return fallback


SYSTEM_PROMPT = (
    "You extract structured job-posting data. Reply with JSON only, no prose. "
    "Keys: company, role, location, seniority, work_mode, salary_low, salary_high, "
    "currency, deadline (YYYY-MM-DD or null), url, contact, skills (array of lowercase "
    "strings). Use null when a field is unknown and never invent a value."
)


def parse_with_llm(text: str, api_key: str | None = None, model: str | None = None,
                   timeout: float = 20.0) -> JobPosting:
    """Extract via an OpenAI-compatible endpoint, falling back to the heuristics."""
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key or not text.strip():
        return parse_heuristic(text)

    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model or os.environ.get("JOBPILOT_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[:8000]},
        ],
    }
    try:
        import httpx  # noqa: PLC0415

        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception:
        return parse_heuristic(text)

    fallback = parse_heuristic(text)
    posting = JobPosting(
        company=str(data.get("company") or fallback.company),
        role=str(data.get("role") or fallback.role),
        location=str(data.get("location") or fallback.location),
        seniority=str(data.get("seniority") or fallback.seniority),
        work_mode=str(data.get("work_mode") or fallback.work_mode),
        salary_low=_as_int(data.get("salary_low"), fallback.salary_low),
        salary_high=_as_int(data.get("salary_high"), fallback.salary_high),
        currency=str(data.get("currency") or fallback.currency),
        deadline=data.get("deadline") or fallback.deadline,
        url=str(data.get("url") or fallback.url),
        contact=str(data.get("contact") or fallback.contact),
        skills=[str(s).lower() for s in (data.get("skills") or fallback.skills)],
        source="llm",
    )
    return posting
