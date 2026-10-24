"""Unit tests for code/intent.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from code.intent import classify_all_requests, classify_intent_offline
from code.loader import load_dataset


class TestIntent(unittest.TestCase):
    def test_samples_all_delete(self):
        """All 32 samples in sample_deletion_requests must be classified as DELETE."""
        ds = load_dataset()
        for req in ds.sample_requests:
            cid = req["case_id"]
            txt = req["request_text"]
            res = classify_intent_offline(cid, txt)
            self.assertEqual(
                res.intent,
                "DELETE",
                f"Sample case {cid} should be DELETE, got {res.intent} ({res.reason})",
            )

    def test_custom_cases_benchmark(self):
        """Custom multilingual benchmark cases must achieve >= 95% accuracy."""
        cases_path = (
            Path(__file__).resolve().parent.parent
            / "evaluation"
            / "custom_cases"
            / "intent_cases.json"
        )
        with open(cases_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        correct = 0
        total = len(cases)
        for i, c in enumerate(cases):
            res = classify_intent_offline(f"custom_{i}", c["text"])
            if res.intent == c["expected"]:
                correct += 1
            else:
                print(f"FAILED: {c['text']} -> expected {c['expected']}, got {res.intent}")

        acc = correct / total
        self.assertGreaterEqual(
            acc, 0.95, f"Accuracy {acc:.2%} is below 95% threshold ({correct}/{total})"
        )

    def test_dataset_non_deletion_count(self):
        """Exactly 10 specific non-deletion requests exist in the 518 dataset."""
        ds = load_dataset()
        results = classify_all_requests(ds.requests)
        non_del_cases = [cid for cid, r in results.items() if r.intent == "NOT_DELETE"]
        expected_non_del = {
            "case_533",
            "case_534",
            "case_535",
            "case_536",
            "case_537",
            "case_538",
            "case_539",
            "case_540",
            "case_541",
            "case_542",
        }
        self.assertEqual(
            set(non_del_cases),
            expected_non_del,
            f"Non-deletion cases mismatch: got {non_del_cases}",
        )

    def test_multilingual_generalization(self):
        """Test at least 2 non-deletion and 2 positive DELETE phrasings per language (6 languages).

        Languages: English, Spanish, French, Portuguese, Japanese, Korean.
        Ensures positive DELETE requests are NOT falsely flagged as NOT_DELETE.
        """
        multilingual_phrasings = [
            # English
            ("Please delete my account and all associated personal data permanently.", "DELETE"),
            ("Kindly erase my user profile and remove all data from your servers.", "DELETE"),
            ("Please do not delete my account, I just want to update my phone number.", "NOT_DELETE"),
            ("I want to keep my profile active, please just unsubscribe me from promotional emails.", "NOT_DELETE"),

            # Spanish
            ("Por favor eliminen mi cuenta y todos mis datos personales de forma definitiva.", "DELETE"),
            ("Solicito borrar mi perfil de usuario y cancelar mi registro.", "DELETE"),
            ("No borrar mi cuenta, solo quiero cambiar mi direccion de entrega.", "NOT_DELETE"),
            ("Deseo mantener mi cuenta activa pero cancelar suscripcion a correos promocionales.", "NOT_DELETE"),

            # French
            ("Veuillez supprimer definitivement mon compte et l'ensemble de mes donnees personnelles.", "DELETE"),
            ("Je demande l'effacement complet de mon profil utilisateur.", "DELETE"),
            ("Ne pas supprimer mon compte, veuillez juste corriger mon numero de telephone.", "NOT_DELETE"),
            ("Je souhaite garder mon compte actif mais arreter les e-mails promotionnels.", "NOT_DELETE"),

            # Portuguese
            ("Solicito a exclusao definitiva da minha conta e de todos os meus dados.", "DELETE"),
            ("Por favor apague meu perfil e remova meus registros do sistema.", "DELETE"),
            ("Nao excluir minha conta, apenas alterar meu endereco de entrega.", "NOT_DELETE"),
            ("Quero manter minha conta ativa, favor cancelar apenas a newsletter.", "NOT_DELETE"),

            # Japanese
            ("アカウントとすべての個人データを完全に削除してください。", "DELETE"),
            ("退会手続きを行い、私のプロファイルを完全に消去することを要求します。", "DELETE"),
            ("アカウントを削除しないでください。パスワードのリセットを手伝ってください。", "NOT_DELETE"),
            ("アカウントは残してください。登録メールアドレスの変更のみをお願いします。", "NOT_DELETE"),

            # Korean
            ("내 계정과 모든 개인정보를 완전히 삭제하고 탈퇴 처리해 주세요.", "DELETE"),
            ("개인 데이터 영구 삭제 및 회원 탈퇴를 요청합니다.", "DELETE"),
            ("계정을 삭제하지 마세요. 배송지 주소만 변경하고 싶습니다.", "NOT_DELETE"),
            ("계정을 유지하고 싶습니다. 마케팅 수신 거부만 처리해 주세요.", "NOT_DELETE"),
        ]

        for text, expected in multilingual_phrasings:
            res = classify_intent_offline("test_case", text)
            self.assertEqual(
                res.intent,
                expected,
                f"Failed for text: '{text}'. Expected {expected}, got {res.intent} ({res.reason})",
            )


if __name__ == "__main__":
    unittest.main()
