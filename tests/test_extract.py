from datetime import date

from jobpilot.extract import parse_heuristic

POSTING = """\
Senior Frontend Engineer
at Northwind Labs
Location: Karachi, Pakistan (Hybrid)
Salary: PKR 350,000 - 500,000 per month

We are hiring a senior frontend engineer to own our design system.
You will work with React, TypeScript, Next.js and Tailwind, and help
migrate legacy pages onto the new component library.

Requirements:
- 4+ years with React and TypeScript
- Comfortable with Figma handoff and accessibility
- Bonus: Node.js, Playwright

Apply by 2026-12-15 at https://northwind.example/careers/fe-senior
or email hiring@northwind.example
"""


def test_extracts_role_and_company():
    posting = parse_heuristic(POSTING)
    assert "frontend engineer" in posting.role.lower()
    assert posting.company == "Northwind Labs"


def test_extracts_salary_range_and_currency():
    posting = parse_heuristic(POSTING)
    assert posting.salary_low == 350_000
    assert posting.salary_high == 500_000
    assert posting.currency == "PKR"


def test_extracts_deadline_url_and_contact():
    posting = parse_heuristic(POSTING, today=date(2026, 11, 3))
    assert posting.deadline == "2026-12-15"
    assert posting.url.startswith("https://northwind.example")
    assert posting.contact == "hiring@northwind.example"


def test_detects_seniority_mode_and_skills():
    posting = parse_heuristic(POSTING)
    assert posting.seniority == "senior"
    assert posting.work_mode == "hybrid"
    assert {"react", "typescript", "next.js", "tailwind", "figma"} <= set(posting.skills)


def test_past_deadline_is_ignored():
    text = "Backend Developer at Acme. Apply by 2024-01-05"
    posting = parse_heuristic(text, today=date(2026, 11, 3))
    assert posting.deadline is None


def test_empty_text_returns_empty_record():
    posting = parse_heuristic("   ")
    assert posting.company == "" and posting.role == ""


def test_k_shorthand_salary():
    posting = parse_heuristic("React Developer at Delta. Salary: USD 80k - 110k")
    assert posting.salary_low == 80_000
    assert posting.salary_high == 110_000


def test_indian_style_thousands_separator():
    posting = parse_heuristic("Python Developer at Epsilon. Salary: PKR 1,20,000")
    assert posting.salary_low == 120_000
