from django import forms
from django.utils.translation import pgettext_lazy

from payments.forms import CreditCardPaymentFormWithName


class BrandType:
    VISA = 'VISA'
    MASTERCARD = 'MASTER'
    AMERICAN_EXPRESS = 'AMEX'

    CHOICES = [
        (VISA, pgettext_lazy('brand type', 'Visa')),
        (MASTERCARD, pgettext_lazy('brand type', 'Mastercard')),
        (AMERICAN_EXPRESS, pgettext_lazy('brand type', 'American Express')),
    ]


class PaymentForm(CreditCardPaymentFormWithName):
    def __init__(self, checkout_id, **kwargs):
        super(PaymentForm, self).__init__(**kwargs)
        self.checkout_id = checkout_id

    VALID_TYPES = ['visa', 'mastercard', 'amex']
    checkout_id = forms.CharField(max_length=48)
