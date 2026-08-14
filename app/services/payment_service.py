from datetime import datetime
from ..extensions import db
from ..models import Payment, PaymentStatus, OrderStatus
from .wallet_service import credit_sale
from .notification_service import notify


def approve_manual(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        raise ValueError('Payment topilmadi.')
    if payment.status == PaymentStatus.APPROVED.value:
        return payment.order
    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("Payment holati o'zgartirib bo'lmaydi.")
    if not payment.receipt:
        raise ValueError('Chek mavjud emas.')

    order = payment.order
    payment.status = PaymentStatus.APPROVED.value
    payment.approved_at = datetime.utcnow()
    order.status = OrderStatus.COMPLETED.value
    for item in order.items:
        credit_sale(item.seller.user, item.seller_amount, order.id)
        notify(item.seller.user_id, 'Yangi sotuv', f'Order #{order.order_code} bo‘yicha {item.seller_amount} UZS daromad yozildi.')
    notify(order.buyer_id, 'Xarid tasdiqlandi', f'Order #{order.order_code} tayyor. Fayllarni yuklashingiz mumkin.')
    return order


def reject_manual(payment_id, reason=''):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        raise ValueError('Payment topilmadi.')
    if payment.status == PaymentStatus.APPROVED.value:
        raise ValueError('Approved paymentni reject qilib bo‘lmaydi.')
    payment.status = PaymentStatus.REJECTED.value
    payment.order.status = OrderStatus.PENDING_PAYMENT.value
    notify(payment.order.buyer_id, 'To‘lov rad etildi', reason or 'Chek tasdiqlanmadi.')
