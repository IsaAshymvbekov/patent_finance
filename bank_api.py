# services/bank_api.py
import requests
from dataclasses import dataclass
from django.conf import settings

BANK_API_URL = "https://api.bank.local"
BANK_API_TOKEN = "super-secret-token"
BANK_CALLBACK_URL = "https://your-domain.com/api/bank/callback/"
BANK_WEBHOOK_SECRET = "super-secret-webhook-key"  # для подписи (см. ниже)


@dataclass
class BankPaymentResult:
    bank_payment_id: str
    pay_url: str


def create_bank_payment(*, payment) -> BankPaymentResult:
    """
    Создание платежа в системе банка.
    """
    url = settings.BANK_API_URL + "/v1/payments"
    payload = {
        "amount": str(payment.amount),
        "currency": "KGS",
        "description": f"Оплата патента #{payment.patent_id}",
        "payment_code": payment.payment_code,
        "callback_url": settings.BANK_CALLBACK_URL,
    }
    headers = {
        "Authorization": f"Bearer {settings.BANK_API_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    return BankPaymentResult(
        bank_payment_id=data["id"],
        pay_url=data["pay_url"],
    )
