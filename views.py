# views.py
import hmac
import hashlib
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils.encoding import force_bytes

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Patent, Payment
from .serializers import (
    PatentCreateSerializer,
    PatentSerializer,
    PaymentInitSerializer,
    BankCallbackSerializer,
)
from .bank_api import create_bank_payment

logger = logging.getLogger(__name__)


class PatentViewSet(viewsets.ModelViewSet):
    queryset = Patent.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Patent.objects.filter(taxpayer=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return PatentCreateSerializer
        return PatentSerializer

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """
        Инициализация оплаты патента через API банка.

        POST /api/patents/{id}/pay/
        """
        patent = self.get_object()
        if patent.is_paid:
            return Response(
                {"detail": "Патент уже оплачен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PaymentInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 1. Создаём локальный Payment
        payment = Payment.objects.create(
            patent=patent,
            amount=patent.amount,
            payment_code=Payment.generate_payment_code(),
            status=Payment.Status.NEW,
        )

        # 2. Регистрируем платёж в банке
        bank_result = create_bank_payment(payment=payment)

        # 3. Обновляем платеж
        payment.bank_payment_id = bank_result.bank_payment_id
        payment.status = Payment.Status.PENDING
        payment.save(update_fields=["bank_payment_id", "status"])

        return Response(
            {
                "patent_id": patent.id,
                "payment_id": payment.id,
                "payment_code": payment.payment_code,
                "status": payment.status,
                "bank_pay_url": bank_result.pay_url,
            },
            status=status.HTTP_201_CREATED,
        )


# ====== CALLBACK ИЗ БАНКА ======

def verify_webhook_signature(request) -> bool:
    """
    Пример проверки подписи вебхука от банка.
    Допустим, банк присылает заголовок:
        X-Signature: hex(HMAC_SHA256(body, BANK_WEBHOOK_SECRET))
    """
    secret = getattr(settings, "BANK_WEBHOOK_SECRET", None)
    if not secret:
        # Если не настроили секрет — принимаем всё (но лучше не так)
        return True

    signature = request.headers.get("X-Signature")
    if not signature:
        return False

    body_bytes = request.body
    expected = hmac.new(
        key=force_bytes(secret),
        msg=body_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # сравниваем безопасно
    return hmac.compare_digest(signature, expected)


class BankCallbackView(APIView):
    """
    URL, который вызывает банк после изменения статуса платежа.

    POST /api/bank/callback/

    Тело (пример):
    {
      "payment_id": "BANK-123",
      "status": "PAID",
      "amount": "5000.00"
    }
    """

    permission_classes = [AllowAny]  # банк не аутентифицирован через JWT

    def post(self, request, *args, **kwargs):
        # 1. Проверка подписи (по желанию)
        if not verify_webhook_signature(request):
            logger.warning("Bank callback: invalid signature")
            return Response(
                {"detail": "invalid signature"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Валидация данных
        serializer = BankCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        bank_payment_id = data["payment_id"]
        status_from_bank = data["status"]
        amount_from_bank: Decimal = data["amount"]

        # 3. Ищем платёж
        try:
            payment = Payment.objects.select_related("patent").get(
                bank_payment_id=bank_payment_id
            )
        except Payment.DoesNotExist:
            logger.error("Bank callback: payment not found %s", bank_payment_id)
            # Можно вернуть 404, но банки обычно ожидают 200, чтобы не ретраить вечно
            return Response(
                {"detail": "payment not found"},
                status=status.HTTP_200_OK,
            )

        # 4. Проверяем сумму (без фанатизма, просто для порядка)
        if payment.amount != amount_from_bank:
            logger.error(
                "Bank callback: amount mismatch. Local=%s, Bank=%s, payment_id=%s",
                payment.amount,
                amount_from_bank,
                payment.id,
            )
            # Можно зафейлить платёж
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            return Response(
                {"detail": "amount mismatch"},
                status=status.HTTP_200_OK,
            )

        # 5. Обновляем статус платежа и патента (idempotent)
        with transaction.atomic():
            if status_from_bank == "PAID":
                # если уже оплачен — ничего не делаем, просто 200
                if payment.status != Payment.Status.PAID:
                    payment.status = Payment.Status.PAID
                    payment.save(update_fields=["status"])

                    patent = payment.patent
                    if not patent.is_paid:
                        patent.is_paid = True
                        patent.save(update_fields=["is_paid"])

                logger.info("Bank callback: payment %s marked as PAID", payment.id)

            elif status_from_bank == "FAILED":
                if payment.status != Payment.Status.PAID:
                    payment.status = Payment.Status.FAILED
                    payment.save(update_fields=["status"])
                logger.info("Bank callback: payment %s marked as FAILED", payment.id)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)
