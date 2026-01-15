# serializers.py
from rest_framework import serializers
from .models import Patent, Payment


class PatentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patent
        fields = ("id", "inn", "period_start", "period_end", "amount")

    def create(self, validated_data):
        user = self.context["request"].user
        return Patent.objects.create(taxpayer=user, **validated_data)


class PatentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patent
        fields = ("id", "inn", "period_start", "period_end", "amount", "is_paid")


class PaymentInitSerializer(serializers.Serializer):
    """
    Пока без полей — всё берём из патента.
    Если что — сюда можно добавить, например, способ оплаты.
    """
    pass


class BankCallbackSerializer(serializers.Serializer):
    """
    Схема JSON, который шлёт банк на callback.
    Пример:
    {
      "payment_id": "BANK-123",   # bank_payment_id
      "status": "PAID",           # или "FAILED"
      "amount": "5000.00"
    }
    """
    payment_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["PAID", "FAILED"])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
