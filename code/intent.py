"""Intent classifier for deletion requests (multilingual generalized rules + Grok integration)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from code.usage import UsageLedger


@dataclass
class IntentResult:
    case_id: str
    intent: str  # "DELETE" or "NOT_DELETE"
    reason: str


# General multilingual non-deletion rules (English, Spanish, French, Portuguese, Japanese, Korean)
# Categories:
# 1. Negation of deletion/closing + desire to keep/retain/continue account
# 2. Change / correct / update / replace profile fields (phone, address, surname, email)
# 3. Marketing / newsletter opt-out only
# 4. Data access / copy / export request (GDPR Art 15, not Art 17)
# 5. Login / access / password reset help without closure
GENERAL_NON_DELETE_RULES = [
    # --- English ---
    # Explicit negation / keep account
    r"\b(?:do\s*not|don\'?t)\s*(?:delete|erase|close|remove|purge)\b",
    r"\b(?:keep|retain|leave)\s+(?:the|my)\s+(?:account|profile|records?)\b",
    r"\bnot\s+(?:asking|a\s+request)\s+to\s+(?:delete|erase|close)\b",
    r"\bcontinue\s+using\s+(?:the\s+service|my\s+account)\b",
    r"\bwithout\s+(?:removing|deleting|erasing)\s+(?:any\s+of\s+)?my\b",
    # Profile update / correction
    r"\b(?:misspelled|correct|update|change|replace)\s+(?:my\s+)?(?:surname|name|phone|mobile|address|email)\b",
    r"\b(?:phone|mobile|number|address|email)\s+(?:is\s+)?(?:out\s+of\s+date|changed)\b",
    # Marketing opt-out only
    r"\b(?:marketing|promotional|newsletter|subscription)\s+(?:list|email|message)?s?\s*(?:only)?\b.*\b(?:opt[-\s]?out|unsubscribe|stop)\b",
    r"\b(?:stop|remove\s+me\s+from)\s+(?:the\s+)?(?:promotional|marketing|newsletter)\b",
    # Data access / export (not deletion)
    r"\b(?:download|copy|export|access)\s+(?:of\s+)?(?:my\s+)?(?:account\s+information|data|invoices?|records?)\b",
    r"\binformation\s+request\b",
    # Login help
    r"\b(?:can\'?t|cannot)\s+access\b.*\b(?:reset|login|password)\b",
    r"\breset(?:ting)?\s+(?:the\s+)?(?:login|password|credentials?)\b",

    # --- Spanish ---
    r"\bno\s+(?:borr(?:ar|en|es)|elimin(?:ar|en|es)|cierr(?:en|es))\b",
    r"\bmantener\s+(?:mi|la)\s+cuenta\b",
    r"\b(?:solo|sólo)\s+(?:quiero\s+)?(?:cambiar|actualizar|corregir)\b",
    r"\b(?:solo|sólo)\s+cancelar\s+suscripci[oó]n\b",
    r"\b(?:ayuda|recuperar)\s+(?:para\s+)?(?:iniciar\s+sesi[oó]n|contrase[nñ]a)\b",

    # --- French ---
    r"\bne\s+pas\s+(?:supprimer|effacer|fermer)\b",
    r"\bne\s+(?:fermez|supprimez)\s+pas\b",
    r"\bgarder\s+(?:mon|le)\s+compte\b",
    r"\b(?:mise\s+[aà]\s+jour|corriger|modifier)\s+(?:mon|mes|le)?\b",
    r"\b(?:uniquement|seulement)\s+(?:les?\s+)?(?:e-?mails?\s+promotionnels?|newsletter)\b",
    r"\baide\s+pour\s+(?:mot\s+de\s+passe|connexion)\b",

    # --- Portuguese ---
    r"\bn[aã]o\s+(?:excluir|deletar|fechar|apagar)\b",
    r"\bmanter\s+(?:minha|a)\s+conta\b",
    r"\bapenas\s+(?:alterar|atualizar|corrigir|mudar)\b",
    r"\bcancelar\s+apenas\s+(?:a\s+)?newsletter\b",

    # --- Japanese ---
    r"(?:削除|解約|退会|消去)しないで",
    r"アカウントを保持",
    r"アカウントは残して",
    r"(?:メールアドレス|電話番号|住所|氏名)の(?:変更|更新|訂正)",
    r"パスワードの(?:リセット|再設定)",
    r"メルマガの(?:解除|配信停止)のみ",

    # --- Korean ---
    r"(?:삭제|탈퇴|해지)하지\s*마세요",
    r"계정을\s*유지",
    r"계정은\s*그대로",
    r"탈퇴가\s*아닙니다",
    r"(?:전화번호|이메일|주소|이름)(?:만)?\s*(?:변경|수정|교체)",
    r"비밀번호\s*(?:재설정|초기화)",
    r"마케팅\s*수신\s*거부만",
]

COMPILED_RULES = [re.compile(p, re.IGNORECASE) for p in GENERAL_NON_DELETE_RULES]


def classify_intent_offline(case_id: str, request_text: str) -> IntentResult:
    """Classify request intent offline using generalized multilingual rule patterns."""
    text = request_text.strip()
    for cp in COMPILED_RULES:
        if cp.search(text):
            return IntentResult(
                case_id=case_id,
                intent="NOT_DELETE",
                reason=f"Matched non-deletion rule: {cp.pattern[:30]}",
            )
    return IntentResult(
        case_id=case_id,
        intent="DELETE",
        reason="Requests account or data erasure",
    )


def classify_all_requests_hybrid(
    requests: List[Dict[str, str]],
    use_llm: bool = False,
    usage_ledger: Optional[UsageLedger] = None,
    classify_activity_emails: Optional[Set[str]] = None,
    disagreements_log_path: Optional[Path] = None,
) -> Dict[str, IntentResult]:
    """Classify all requests combining deterministic patterns, Grok LLM (if enabled), and activity cross-check.

    Decision logic:
    - If LLM not enabled or fails/no key: use deterministic classifier.
    - If LLM enabled: run both.
      - If they agree: use it.
      - If they disagree: cross-check with system_activity.csv CLASSIFY_REQUEST events;
        otherwise prefer Grok. Log disagreements to intent_disagreements.md.
    """
    from code.llm import classify_intent_grok

    results: Dict[str, IntentResult] = {}
    disagreements: List[Dict[str, Any]] = []

    model_name = os.environ.get("GROK_MODEL", "grok-beta")

    for req in requests:
        cid = req.get("case_id", "")
        txt = req.get("request_text", "")
        email = req.get("email", "").strip().lower()

        det_res = classify_intent_offline(cid, txt)
        chosen_res = det_res

        if use_llm:
            try:
                grok_dict, prompt_tok, comp_tok, cost, from_cache = classify_intent_grok(
                    txt, model_name=model_name
                )
                if usage_ledger:
                    if from_cache:
                        usage_ledger.record_cache_hit(model_name)
                    else:
                        usage_ledger.record_call(model_name, prompt_tok, comp_tok, cost)

                grok_intent = grok_dict.get("intent", "DELETE").upper()
                grok_reason = grok_dict.get("reason", "Classified by Grok")

                if grok_intent == det_res.intent:
                    chosen_res = IntentResult(case_id=cid, intent=grok_intent, reason=grok_reason)
                else:
                    # Disagreement!
                    has_activity_non_del = bool(classify_activity_emails and email in classify_activity_emails)
                    if has_activity_non_del:
                        final_intent = "NOT_DELETE"
                        final_reason = "Resolved via system_activity CLASSIFY_REQUEST cross-check"
                    else:
                        # Prefer Grok
                        final_intent = grok_intent
                        final_reason = f"Grok preferred: {grok_reason}"

                    disagreements.append({
                        "case_id": cid,
                        "email": email,
                        "text": txt,
                        "deterministic": det_res.intent,
                        "grok": grok_intent,
                        "activity_crosscheck": "NOT_DELETE" if has_activity_non_del else "NONE",
                        "chosen": final_intent,
                        "reason": final_reason,
                    })
                    chosen_res = IntentResult(case_id=cid, intent=final_intent, reason=final_reason)
            except Exception as e:
                # LLM call or config failed -> fallback to deterministic
                if usage_ledger:
                    usage_ledger.record_api_error(model_name)
                chosen_res = det_res

        # Fallback activity check if still DELETE but activity says non-deletion
        if classify_activity_emails and email in classify_activity_emails:
            if chosen_res.intent != "NOT_DELETE":
                chosen_res = IntentResult(
                    case_id=cid,
                    intent="NOT_DELETE",
                    reason="Classified non-deletion by privacy intake activity",
                )

        results[cid] = chosen_res

    # Log disagreements if any
    if disagreements_log_path:
        disagreements_log_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Intent Classification Disagreements Log",
            "",
            f"**Total Disagreements:** {len(disagreements)}",
            "",
            "| Case ID | Deterministic | Grok | Activity Cross-Check | Final Chosen | Text Excerpt |",
            "|---|---|---|---|---|---|",
        ]
        for d in disagreements:
            excerpt = d["text"].replace("\n", " ")[:60]
            lines.append(
                f"| `{d['case_id']}` | {d['deterministic']} | {d['grok']} | {d['activity_crosscheck']} | **{d['chosen']}** | {excerpt}... |"
            )
        disagreements_log_path.write_text("\n".join(lines), encoding="utf-8")

    return results


def classify_all_requests(
    requests: List[Dict[str, str]],
    classify_activity_emails: Optional[Set[str]] = None,
) -> Dict[str, IntentResult]:
    """Backward compatibility wrapper for offline batch classification."""
    return classify_all_requests_hybrid(
        requests,
        use_llm=False,
        classify_activity_emails=classify_activity_emails,
    )
