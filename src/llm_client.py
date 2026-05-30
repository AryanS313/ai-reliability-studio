from __future__ import annotations

import time

from src import config
from src.utils import normalize_text


def build_final_prompt(system_prompt: str, context: str, question: str) -> str:
    return f"""{system_prompt.strip()}

Retrieved context:
{context.strip() or "No relevant context retrieved."}

User question:
{question}

Assistant answer:"""


def generate_answer(
    question: str,
    context: str,
    system_prompt: str,
    model_name: str,
    api_key: str | None = None,
) -> dict:
    final_prompt = build_final_prompt(system_prompt, context, question)
    effective_api_key = api_key or config.OPENAI_API_KEY
    if model_name != "mock-model" and effective_api_key:
        try:
            result = _openai_answer(final_prompt, model_name, effective_api_key)
            result["final_prompt"] = final_prompt
            return result
        except Exception as exc:
            fallback = _mock_answer(question, context, system_prompt, "mock-model")
            fallback["answer"] += f"\n\n[System note: OpenAI call failed; mock fallback used. {exc}]"
            fallback["final_prompt"] = final_prompt
            return fallback
    result = _mock_answer(question, context, system_prompt, model_name)
    result["final_prompt"] = final_prompt
    return result


def _openai_answer(prompt: str, model_name: str, api_key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    start = time.perf_counter()
    try:
        response = client.responses.create(model=model_name, input=prompt)
        answer = response.output_text
        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", None)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", None)
    except AttributeError:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        answer = response.choices[0].message.content or ""
        input_tokens = getattr(response.usage, "prompt_tokens", None) if response.usage else None
        output_tokens = getattr(response.usage, "completion_tokens", None) if response.usage else None

    latency_ms = (time.perf_counter() - start) * 1000
    input_tokens = input_tokens or config.approx_tokens(prompt)
    output_tokens = output_tokens or config.approx_tokens(answer)
    return {
        "answer": answer,
        "model": model_name,
        "latency_ms": round(latency_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": round(config.estimate_cost(model_name, input_tokens, output_tokens), 6),
    }


def _mock_answer(question: str, context: str, system_prompt: str, requested_model: str) -> dict:
    start = time.perf_counter()
    strict = _is_strict_prompt(system_prompt)
    q = normalize_text(question)
    source = _best_source(q, context)
    needs_escalation = _needs_escalation(q)
    insufficient = _is_out_of_scope(q) or not context.strip()

    if strict:
        answer = _strict_response(q, source, needs_escalation, insufficient)
    else:
        answer = _basic_response(q, source, needs_escalation, insufficient)

    latency_ms = (time.perf_counter() - start) * 1000 + (48 if strict else 30)
    input_tokens = config.approx_tokens(system_prompt + context + question)
    output_tokens = config.approx_tokens(answer)
    return {
        "answer": answer,
        "model": "mock-model",
        "latency_ms": round(latency_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": 0.0,
    }


def _is_strict_prompt(system_prompt: str) -> bool:
    text = normalize_text(system_prompt)
    return "responsible ai assistant" in text or "escalation required" in text or "answer only using" in text


def _best_source(q: str, context: str) -> str:
    if any(term in q for term in ["refund", "charged twice", "chargeback", "transaction id", "duplicate payment"]):
        return "Refund Policy"
    if any(term in q for term in ["kyc", "pan", "aadhaar", "id", "document", "name", "address proof"]):
        return "KYC Policy"
    if any(term in q for term in ["loan", "credit", "income", "debt", "approval", "rejected", "reconsideration"]):
        return "Loan Rejection SOP"
    if any(term in q for term in ["close", "closure", "active loan", "open dispute", "pending transactions"]):
        return "Account Closure Policy"
    if any(term in q for term in ["legal", "fraud", "compliance", "eligibility", "confidence", "escalat", "threat", "complaint", "regulator"]):
        return "Customer Support Escalation SOP"
    for candidate in [
        "Refund Policy",
        "KYC Policy",
        "Loan Rejection SOP",
        "Account Closure Policy",
        "Customer Support Escalation SOP",
    ]:
        if candidate in context:
            return candidate
    return "Customer Support Escalation SOP"


def _needs_escalation(q: str) -> bool:
    triggers = [
        "fraud",
        "after 10 days",
        "chargeback",
        "threat",
        "complaint",
        "ignore the policy",
        "manual",
        "approve",
        "reverse",
        "rejected",
        "rejection",
        "threshold",
        "guarantee",
        "dispute",
        "legal",
        "compliance",
        "identity mismatch",
        "name on aadhaar does not match",
        "duplicate id",
        "suspicious",
        "final",
        "eligibility",
        "best decision",
        "is my case safe",
        "policy for my issue",
        "qualify",
        "low confidence",
        "regulator",
    ]
    return any(trigger in q for trigger in triggers)


def _is_out_of_scope(q: str) -> bool:
    return any(term in q for term in ["flight", "weather", "poem", "pricing plan", "password", "office address"])


def _strict_response(q: str, source: str, needs_escalation: bool, insufficient: bool) -> str:
    if insufficient:
        return (
            "Answer: I do not have enough information in the uploaded documents to answer this confidently.\n"
            "Sources: Out of Scope\n"
            "Escalation Required: No\n"
            "Reason: The uploaded documents do not contain enough information for this request."
        )
    fact = _policy_fact(q, source)
    escalation = "Yes" if needs_escalation else "No"
    reason = "This involves review, dispute, approval, compliance, fraud, identity, or final-decision risk." if needs_escalation else "The retrieved policy supports a factual answer without final approval."
    return f"Answer: {fact}\nSources: {source}\nEscalation Required: {escalation}\nReason: {reason}"


def _basic_response(q: str, source: str, needs_escalation: bool, insufficient: bool) -> str:
    if insufficient:
        return "I can try to help with that, but I do not see the exact details in the support documents."
    if "approve" in q and "loan" in q:
        return "Your rejected loan may be approved manually if updated documents are accepted."
    if "ignore the policy" in q:
        return "I can make an exception if the request seems reasonable."
    if "final" in q and ("loan" in q or "close" in q or "eligible" in q):
        return "Based on the policy, you may be eligible."
    fact = _policy_fact(q, source)
    if needs_escalation and source in {"Refund Policy", "Account Closure Policy", "KYC Policy"}:
        return f"{fact} This may need review."
    return fact


def _policy_fact(q: str, source: str) -> str:
    if source == "Refund Policy":
        if "30 days" in q:
            return "Refunds after 30 days are generally not eligible unless fraud is suspected."
        if "10 days" in q or "after 7 days" in q:
            return "Refund requests after 7 days require support review before a decision can be communicated."
        if "fraud" in q:
            return "Fraud-related refund claims must be escalated to human support review."
        if "duplicate" in q:
            return "Duplicate payment refund requests require transaction verification before any refund decision."
        if "transaction id" in q or "cite" in q:
            return "Refund decisions must cite the transaction ID and policy reason."
        if "promise" in q:
            return "The assistant must not promise that a refund will be approved."
        return "Refunds are allowed within 7 days when the payment was completed successfully and the customer provides a valid transaction ID."
    if source == "KYC Policy":
        if "missing" in q:
            return "KYC cannot be approved if mandatory documents are missing."
        if "name" in q or "mismatch" in q:
            return "Name mismatch requires manual review before KYC can be completed."
        if "duplicate" in q or "suspicious" in q or "tampered" in q:
            return "Duplicate, suspicious, tampered, or unverifiable ID documents require compliance escalation."
        if "unreadable" in q or "cropped" in q or "blurred" in q or "expired" in q or "pending" in q:
            return "Incomplete, unreadable, blurred, cropped, or expired documents lead to pending KYC status."
        if "override" in q:
            return "The assistant must not approve KYC or override compliance checks."
        return "PAN, Aadhaar, and valid address proof are required for KYC verification."
    if source == "Loan Rejection SOP":
        if "threshold" in q:
            return "The assistant must not disclose internal credit scoring thresholds."
        if "approve" in q or "manual" in q or "reverse" in q or "dispute" in q or "reconsideration" in q:
            return "The assistant must not manually approve loans, and reconsideration or dispute requests must be escalated to credit review."
        if "guarantee" in q:
            return "The assistant must not promise or guarantee loan approval."
        if "final" in q or "eligibility" in q:
            return "Final loan eligibility decisions require human review."
        if "update" in q:
            return "Customers may update income proof, complete KYC, and correct inconsistent application information."
        return "Common loan rejection reasons include low credit score, insufficient income proof, failed KYC, high existing debt, or inconsistent application information."
    if source == "Account Closure Policy":
        if "active loan" in q:
            return "Account closure is blocked if an active loan exists."
        if "open dispute" in q or "dispute" in q:
            return "Account closure is blocked if there is an open dispute."
        if "kyc" in q:
            return "Account closure is blocked if there is an unresolved KYC issue."
        if "fraud" in q:
            return "Account closure is blocked during a fraud investigation and should be escalated."
        if "identity mismatch" in q:
            return "Identity mismatch account closure requests must be escalated to human review."
        if "final" in q or "eligible" in q:
            return "Final account closure eligibility should not be confirmed by the assistant when blockers may exist."
        if "before requesting" in q or "again" in q:
            return "Customers may settle pending transactions, resolve disputes, complete KYC, and clear active loan obligations before requesting closure again."
        return "Customers can request account closure after all pending transactions are settled and required checks are complete."
    if "low confidence" in q or "confidence" in q:
        return "Low-confidence AI answers must be escalated."
    if "source" in q or "documents" in q:
        return "If uploaded documents do not contain a reliable policy source, the assistant should say it does not have enough information and escalate when sensitive."
    if "threat" in q or "complaint" in q or "regulator" in q:
        return "Customer threats, complaints, legal notices, regulator mentions, or urgent harm language require escalation."
    if "facts" in q or "next steps" in q:
        return "The assistant should separate factual policy information from suggested next steps."
    return "Legal, fraud, compliance, rejection, refund dispute, identity mismatch, chargeback, complaint, regulatory language, and final eligibility cases must be escalated."
