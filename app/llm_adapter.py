# app/llm_adapter.py
import os
import json
from typing import Tuple, Dict, List

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Required fields reference from the PDF
REQUIRED_FIELDS = {
    "contract": ["party_1", "party_2", "signature", "date", "payment_terms"],
    "invoice": ["invoice_number", "amount", "due_date", "tax", "bill_to", "bill_from"]
}

def simple_keyword_classifier(text: str) -> Tuple[str, float]:
    """Fallback quick classifier if no LLM key is present."""
    t = text.lower()
    score_contract = 0
    score_invoice = 0
    # very simple heuristics
    for w in ["agreement", "party", "hereby", "witnesseth", "contract"]:
        if w in t: score_contract += 1
    for w in ["invoice", "bill", "amount due", "due date", "tax", "invoice no", "invoice number"]:
        if w in t: score_invoice += 1
    if score_invoice > score_contract:
        confidence = min(0.9, 0.5 + 0.1 * (score_invoice - score_contract))
        return "invoice", confidence
    elif score_contract > 0:
        confidence = min(0.9, 0.5 + 0.1 * (score_contract - score_invoice))
        return "contract", confidence
    else:
        # default to report if neither
        return "report", 0.5

# Optional OpenAI integration (ChatCompletion). If available, use it for better results.
def openai_classify(text: str):
    import openai
    openai.api_key = OPENAI_API_KEY
    system = "You are a helpful document classifier. Classify the document as one of: contract, invoice, report. Return JSON like: {\"type\":\"invoice\",\"confidence\":0.92,\"evidence\":\"...\"}"
    prompt = f"{text[:4000]}\n\nClassify the type and give a confidence between 0 and 1."
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini" if hasattr(openai, 'ChatCompletion') else "gpt-4o",
        messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
        temperature=0
    )
    try:
        txt = resp["choices"][0]["message"]["content"]
        # attempt to parse JSON in the reply
        import re
        match = re.search(r"\{.*\}", txt, re.S)
        if match:
            j = json.loads(match.group())
            return j.get("type", "report"), float(j.get("confidence", 0.0))
    except Exception:
        pass
    # fallback
    return None

def classify_document(text: str) -> Tuple[str, float]:
    if OPENAI_API_KEY:
        out = openai_classify(text)
        if out:
            return out
    # fallback
    return simple_keyword_classifier(text)

def find_missing_fields(text: str, doc_type: str) -> Dict:
    """
    For given doc_type (contract/invoice/report), return a dict with keys:
      - missing_fields: list
      - found_fields: list
      - critical_missing: list (same as missing for us)
      - recommendations: string
    """
    t = text.lower()
    req = REQUIRED_FIELDS.get(doc_type, [])
    found = []
    missing = []
    for field in req:
        # simple heuristics to find field mentions
        if field in ["signature"]:
            # signature detection
            keywords = ["signature", "signed by", "signatures"]
        elif field in ["date", "due_date"]:
            keywords = ["date", "dated", "due date", "due_date", "due"]
        elif field in ["invoice_number"]:
            keywords = ["invoice no", "invoice number", "invoice #", "invoice"]
        elif field in ["amount"]:
            keywords = ["amount", "total", "amount due", "subtotal"]
        elif field in ["tax"]:
            keywords = ["tax", "gst", "vat"]
        elif field in ["bill_to", "bill_from"]:
            keywords = ["bill to", "bill from", "billed to", "billed from", "from:", "to:"]
        elif field in ["payment_terms"]:
            keywords = ["payment terms", "payment due", "terms", "payable"]
        else:
            keywords = [field]

        exists = any(k in t for k in keywords)
        if exists:
            found.append(field)
        else:
            missing.append(field)

    recommendations = []
    if missing:
        recommendations.append(f"Missing required fields for {doc_type}: {', '.join(missing)}.")
        recommendations.append("Add clearly labeled fields (e.g., 'Invoice Number:', 'Amount:', 'Due Date:').")
    else:
        recommendations.append("All required fields present according to heuristics. Verify values and formatting.")

    return {
        "required_fields": req,
        "found_fields": found,
        "missing_fields": missing,
        "critical_missing": missing,  # all required fields are critical per spec
        "recommendations": " ".join(recommendations)
    }
