import logging
import re

import requests
from django.shortcuts import redirect
from payments import PaymentStatus, PaymentError
from payments.core import BasicProvider

from saleor.userprofile.models import UserCard
from .forms import PaymentForm

logger = logging.getLogger(__name__)

# 4005550000000001 05/21 cvv2 123
class PaymentType():
    REFUND = 'RF'
    CAPTURE = 'CP'
    REVERSAL = 'RV'
    DEBIT = "DB"


class HyperPayProvider(BasicProvider):
    def __init__(self, entity_id, password, user_id,
                 url='https://test.oppwa.com/v1/', **kwargs):
        self.user_id = user_id
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

    def success_payment_status(self, code):
        return re.search(r"^(000\.000\.|000\.100\.1|000\.[36])", code) or \
               re.search(r"^(000\.400\.0[^3]|000\.400\.100)", code)

    def _prepare_checkout(self, merchant_id, currency, amount=None, payment_type=PaymentType.DEBIT):
        self.data['amount'] = amount
        self.data["paymentType"] = payment_type
        self.data["currency"] = currency
        self.data["merchantTransactionId"] = merchant_id

        response = requests.post(self.checkout_url, self.data)
        return response.json()

    def _attach_saved_cards(self, registrations=[]):
        for index, register_id in enumerate(registrations):
            self.data["registrations[{}].id".format(str(index))] = register_id

    def get_form(self, payment, data=None):
        if data:
             self._attach_saved_cards(registrations=data.get('registrations'))
        response = self._prepare_checkout(merchant_id=payment.order.pk, currency=payment.currency, amount=payment.total)
        if "id" in response:
            payment.transaction_id = response['id']
            payment.save()
        form = PaymentForm(checkout_id=response.get('id'), payment=payment)
        return form

    def process_data(self, payment, request):
        response = requests.get(self._get_status_url(request.GET.get('id')))
        result = response.json()
        if response.status_code == 200:
            if self.success_payment_status(result['result']['code']):
                payment.change_status(PaymentStatus.CONFIRMED)
                payment.captured_amount = payment.total
                payment.extra_data = result
                payment.transaction_id = result['id']
                payment.save()
                if "registrationId" in result:
                    self._save_card(payment,result)

                return redirect(payment.get_success_url())
            else:
                payment.change_status(PaymentStatus.REJECTED, result['result']['description'])
                payment.extra_data = result
                payment.save()
        else:
            logger.warning("HyperPay Error", extra={
                'response': result,
                'status_code': response.status_code})
            payment.change_status(PaymentStatus.ERROR, result['result']['description'])
        return redirect(payment.get_failure_url())

    def _rebill(self, payment, amount, payment_type):
        self.data["amount"] = amount
        self.data["paymentType"] = payment_type
        self.data["currency"] = payment.currency
        response = requests.post(self.rebill_url.format(payment.transaction_id), self.data)
        return response

    def refund(self, payment, amount):
        response = self._rebill(payment=payment, amount=amount, payment_type=PaymentType.REFUND)
        result = response.json()
        if self.success_payment_status(result['result']['code']):
            payment.change_status(PaymentStatus.REFUNDED)
        else:
            raise PaymentError(result['result']['description'])
        return amount

    # def _save_card(self, payment, resposne):
    #     token = resposne["registrationId"]
    #     card = resposne['card']
    #     expiry_date = card["expiryYear"] + "-" + card["expiryMonth"]
    #     user_card = UserCard()
    #     user_card.token = token
    #     user_card.expiry_date = expiry_date
    #     user_card.last_4_digits = card["last4Digits"]
    #     user_card.bin = card["bin"]
    #     user_card.provider = "hyperpay"
    #     user_card.save()
    #     payment.order.user.payment_cards.add(user_card)
