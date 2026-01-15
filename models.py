from django.conf import settings
from django.db import models
import uuid


class Patent(models.Model):
    """Патент на уплату налога (упрощённо)."""
    taxpayer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patents",
    )
    inn = models.CharField("ИНН", max_length=14)
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Патент {self.id} ({self.inn})"


class Payment(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Создан"
        PENDING = "PENDING", "Ожидает оплаты"
        PAID = "PAID", "Оплачен"
        FAILED = "FAILED", "Ошибка"

    patent = models.ForeignKey(
        Patent,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    payment_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Наш внутренний код платежа",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    bank_payment_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="ID платежа в системе банка",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_payment_code() -> str:
        # Любой формат, главное — уникальный
        return uuid.uuid4().hex[:12].upper()
