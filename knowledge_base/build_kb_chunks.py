"""
build_kb_chunks.py
-------------------
Reads ghana_msme_tax_knowledge_base.json and produces semantically-scoped
text chunks for RAG, driven by an explicit manifest (CHUNK_SPECS) rather
than naive whole-document slicing. Repeated-item arrays (key_deadlines,
key_rates, compliance_faq) are expanded one chunk per item since each is
already a self-contained fact. chatbot_intents and fallback_responses are
UI/meta strings, not facts, so they're excluded from the RAG corpus.

Output
------
  kb_chunks.json — JSON array of:
    {"id": str, "title": str, "source_path": str, "text": str, "word_count": int}

Run:
    python3 knowledge_base/build_kb_chunks.py
"""

import json
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "ghana_msme_tax_knowledge_base.json"
OUTPUT_FILE = Path(__file__).parent / "kb_chunks.json"


# ---------------------------------------------------------------------------
# Rendering — turn a JSON subtree into readable prose
# ---------------------------------------------------------------------------

def humanize(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def render(value, depth: int = 0) -> str:
    indent = "  " * depth
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            label = humanize(k)
            if isinstance(v, (dict, list)):
                lines.append(f"{indent}{label}:")
                lines.append(render(v, depth + 1))
            else:
                lines.append(f"{indent}{label}: {v}")
        return "\n".join(lines)
    elif isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                inline = "; ".join(f"{humanize(k)}: {v}" for k, v in item.items())
                lines.append(f"{indent}- {inline}")
            else:
                lines.append(f"{indent}- {item}")
        return "\n".join(lines)
    else:
        return f"{indent}{value}"


def get_path(kb: dict, dotted: str):
    node = kb
    for part in dotted.split("."):
        node = node[part]
    return node


def build_section_chunk(kb: dict, chunk_id: str, title: str, paths: list[str]) -> dict:
    parts = [render(get_path(kb, p)) for p in paths]
    text = f"{title}\n\n" + "\n\n".join(parts)
    text = text.strip()
    return {
        "id": chunk_id,
        "title": title,
        "source_path": ", ".join(paths),
        "text": text,
        "word_count": len(text.split()),
    }


def build_split_chunks(kb: dict, base_id: str, base_title: str, path: str) -> list[dict]:
    """
    Split a subsection into one chunk per immediate child field, instead of
    merging the whole subsection into a single blob. Used for fact-dense
    subsections (registration rules, rates, deadlines nested under a topic)
    where bundling several distinct facts into one chunk dilutes the
    embedding and hurts retrieval precision for a query about just one of
    those facts.
    """
    node = get_path(kb, path)
    chunks = []
    for key, value in node.items():
        label = humanize(key)
        chunk_title = f"{base_title} — {label}"
        text = f"{chunk_title}\n\n{render(value)}".strip()
        chunks.append({
            "id": f"{base_id}_{key}",
            "title": chunk_title,
            "source_path": f"{path}.{key}",
            "text": text,
            "word_count": len(text.split()),
        })
    return chunks


# ---------------------------------------------------------------------------
# Manifest — one entry per semantically coherent unit
# ---------------------------------------------------------------------------

CHUNK_SPECS = [
    {"id": "tax_system_overview", "title": "Ghana Tax System Overview",
     "paths": ["tax_system_overview"], "split": True},

    # income_tax
    {"id": "income_tax_overview", "title": "Income Tax — Overview",
     "paths": ["income_tax.overview"]},
    {"id": "income_tax_employment", "title": "Income Tax — Employment Income & PAYE",
     "paths": ["income_tax.income_from_employment"], "split": True},
    {"id": "income_tax_business", "title": "Income Tax — Business Income",
     "paths": ["income_tax.income_from_business"], "split": True},
    {"id": "income_tax_investment", "title": "Income Tax — Investment Income",
     "paths": ["income_tax.income_from_investment"], "split": True},
    {"id": "income_tax_exempt_amounts", "title": "Income Tax — Exempt Amounts",
     "paths": ["income_tax.exempt_amounts"]},
    {"id": "income_tax_deductions", "title": "Income Tax — Deductions & Reliefs",
     "paths": ["income_tax.deductions"], "split": True},
    {"id": "income_tax_accounting_methods", "title": "Income Tax — Accounting Methods",
     "paths": ["income_tax.accounting_methods"]},
    {"id": "income_tax_corporate_rates", "title": "Income Tax — Corporate Tax Rates",
     "paths": ["income_tax.corporate_tax_rates"]},
    {"id": "income_tax_young_entrepreneur_relief", "title": "Income Tax — Young Entrepreneur / MSME Relief",
     "paths": ["income_tax.msme_young_entrepreneur_relief"], "split": True},
    {"id": "income_tax_business_structure", "title": "Income Tax — Business Structure Tax Treatment",
     "paths": ["income_tax.business_structure_tax_treatment"], "split": True},
    {"id": "income_tax_withholding", "title": "Income Tax — Withholding Tax",
     "paths": ["income_tax.withholding_tax"], "split": True},
    {"id": "income_tax_anti_avoidance", "title": "Income Tax — Thin Capitalisation & Anti-Avoidance",
     "paths": ["income_tax.thin_capitalisation", "income_tax.anti_avoidance"]},
    {"id": "income_tax_returns_filing", "title": "Income Tax — Returns & Filing",
     "paths": ["income_tax.tax_returns_and_filing"], "split": True},
    {"id": "income_tax_planning_strategies", "title": "Income Tax — Tax Planning Strategies",
     "paths": ["income_tax.tax_planning_strategies"]},

    # vat
    {"id": "vat_overview", "title": "VAT — Overview",
     "paths": ["vat.overview"]},
    {"id": "vat_registration", "title": "VAT — Registration",
     "paths": ["vat.registration"], "split": True},
    {"id": "vat_taxable_supplies", "title": "VAT — Taxable Supplies",
     "paths": ["vat.taxable_supplies"], "split": True},
    {"id": "vat_withholding", "title": "VAT — Withholding",
     "paths": ["vat.vat_withholding"], "split": True},
    {"id": "vat_input_tax_deduction", "title": "VAT — Input Tax Deduction",
     "paths": ["vat.input_tax_deduction"], "split": True},
    {"id": "vat_invoice_requirements", "title": "VAT — Tax Invoice Requirements",
     "paths": ["vat.tax_invoice_requirements"], "split": True},
    {"id": "vat_inclusive_pricing", "title": "VAT — Tax-Inclusive Pricing",
     "paths": ["vat.tax_inclusive_pricing"]},
    {"id": "vat_filing_and_payment", "title": "VAT — Filing & Payment",
     "paths": ["vat.filing_and_payment"], "split": True},

    # free_zones
    {"id": "free_zones_overview", "title": "Free Zones — Overview & Eligibility",
     "paths": ["free_zones.overview", "free_zones.governing_body", "free_zones.who_can_operate",
               "free_zones.restriction"]},
    {"id": "free_zones_permitted_activities", "title": "Free Zones — Permitted Activities",
     "paths": ["free_zones.permitted_activities"]},
    {"id": "free_zones_fiscal_incentives", "title": "Free Zones — Fiscal Incentives",
     "paths": ["free_zones.fiscal_incentives"], "split": True},
    {"id": "free_zones_domestic_sales", "title": "Free Zones — Sales to Domestic Market",
     "paths": ["free_zones.sales_to_domestic_market"]},
    {"id": "free_zones_investor_guarantees", "title": "Free Zones — Investor Guarantees",
     "paths": ["free_zones.guarantees_for_investors"], "split": True},
    {"id": "free_zones_employment", "title": "Free Zones — Employment",
     "paths": ["free_zones.employment"]},
    {"id": "free_zones_licensing", "title": "Free Zones — Licensing",
     "paths": ["free_zones.licensing"], "split": True},

    {"id": "taxpayer_rights_and_obligations", "title": "Taxpayer Rights & Obligations",
     "paths": ["taxpayer_rights_and_obligations"], "split": True},
]

SECTOR_TITLES = {
    "financial_institutions": "Sector Notes — Financial Institutions",
    "petroleum_operations": "Sector Notes — Petroleum Operations",
    "mining_operations": "Sector Notes — Mining Operations",
    "insurance": "Sector Notes — Insurance",
    "retirement_funds": "Sector Notes — Retirement Funds",
    "charitable_organisations": "Sector Notes — Charitable Organisations",
}


def build_array_item_chunks(kb: dict) -> list[dict]:
    chunks = []

    for i, item in enumerate(kb["key_deadlines"], start=1):
        text = (
            f"Ghana tax filing deadline — {item['obligation']}.\n"
            f"Deadline: {item['deadline']}.\n"
            f"Legislation: {item.get('legislation', 'N/A')}."
        )
        chunks.append({
            "id": f"key_deadline_{i}",
            "title": f"Deadline — {item['obligation']}",
            "source_path": f"key_deadlines[{i - 1}]",
            "text": text,
            "word_count": len(text.split()),
        })

    for i, item in enumerate(kb["key_rates"], start=1):
        text = f"Ghana tax rate — {item['tax']}: {item['rate']}."
        chunks.append({
            "id": f"key_rate_{i}",
            "title": f"Rate — {item['tax']}",
            "source_path": f"key_rates[{i - 1}]",
            "text": text,
            "word_count": len(text.split()),
        })

    for i, item in enumerate(kb["compliance_faq"], start=1):
        text = f"Q: {item['question']}\nA: {item['answer']}"
        chunks.append({
            "id": f"compliance_faq_{i}",
            "title": f"FAQ — {item['question']}",
            "source_path": f"compliance_faq[{i - 1}]",
            "text": text,
            "word_count": len(text.split()),
        })

    for key, title in SECTOR_TITLES.items():
        node = kb["sector_specific_notes"][key]
        text = (f"{title}\n\n" + render(node)).strip()
        chunks.append({
            "id": f"sector_{key}",
            "title": title,
            "source_path": f"sector_specific_notes.{key}",
            "text": text,
            "word_count": len(text.split()),
        })

    return chunks


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"[ERROR] Input file not found: {INPUT_FILE}")
        return

    kb = json.loads(INPUT_FILE.read_text(encoding="utf-8"))

    chunks = []
    for spec in CHUNK_SPECS:
        if spec.get("split"):
            chunks += build_split_chunks(kb, spec["id"], spec["title"], spec["paths"][0])
        else:
            chunks.append(build_section_chunk(kb, spec["id"], spec["title"], spec["paths"]))
    chunks += build_array_item_chunks(kb)

    OUTPUT_FILE.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Chunks produced : {len(chunks)}")
    print(f"Output          : {OUTPUT_FILE.name}")
    print()
    for c in chunks:
        preview = c["text"][:80].replace("\n", " ")
        print(f"  {c['id']:38s} ({c['word_count']:>4} words)  {preview}...")


if __name__ == "__main__":
    main()
