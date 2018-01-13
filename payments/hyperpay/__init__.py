import requests
from django.shortcuts import redirect
from enum import Enum

from payments import PaymentStatus, PaymentError
from payments.core import BasicProvider
from .forms import PaymentForm


class HyperPayProvider(BasicProvider):

    class PaymentType(Enum):
        REFUND = 'CP'
        CAPTURE = 'RF'
        REVERSAL = 'RV'

    def __init__(self, entity_id, password,
                 url='https://test.oppwa.com/v1/', **kwargs):
        self.user_id = "8a8294185f5892cb015f6813d4e92732"
        self.password = password
        self.entity_id = entity_id
        self.url = url
        self.checkout_url = self.url + "checkouts"
        self.status_url = self.url + "checkouts/{}/payment?" \
                                     "authentication.userId={}&" \
                                     "authentication.password={}&" \
                                     "authentication.entityId={}"
        self.rebill_url = self.url + "payments/{}"
        self.data = {
            'authentication.userId': self.user_id,
            'authentication.password': self.password,
            'authentication.entityId': self.entity_id,
            # "testMode": "EXTERNAL",
        }

        super(HyperPayProvider, self).__init__(**kwargs)

    def _get_status_url(self, checkout_id):
        return self.status_url.format(str(checkout_id),
                                      self.user_id,
                                      self.password,
                                      self.entity_id)

    def _prepare_checkout(self, currency, shopper_result_url=None, amount=None, payment_type="DB"):
        self.data['amount'] = amount
        self.data["paymentType"] = payment_type
        self.data["currency"] = currency
        response = requests.post(self.url, self.data)
        return response

    def get_form(self, payment, data=None):
        response = self._prepare_checkout(currency=payment.currency, amount=payment.total)
        if 'id' in response:
            payment.transaction_id = response['id']
            payment.save()
        form = PaymentForm(checkout_id=response['id'], payment=payment)
        return form

    def process_data(self, payment, request):
        success_url = payment.get_success_url()
        response = requests.get(self._get_status_url())
        return redirect(success_url)

    def _rebill(self, payment_id, amount, payment_type):
        self.data["amount"] = amount
        self.data["paymentType"] = payment_type
        response = requests.post(self.rebill_url.format(payment_id), self.data)
        return response

    def refund(self, payment, amount):
        response = self._rebill(payment=payment.transaction_id, amount=amount, payment_type=self.PaymentType.REFUND)
        payment.change_status(PaymentStatus.REFUNDED)
        return amount

    def capture(self, payment, amount=None):
        response = self._rebill(payment=payment.transaction_id, amount=amount, payment_type=self.PaymentType.CAPTURE)

        status = response['status']
        if status == 'completed':
            payment.change_status(PaymentStatus.CONFIRMED)
            return amount
        elif status in ['partially_captured', 'partially_refunded']:
            return amount
        elif status == 'pending':
            payment.change_status(PaymentStatus.WAITING)
        elif status == 'refunded':
            payment.change_status(PaymentStatus.REFUNDED)
            raise PaymentError('Payment already refunded')

