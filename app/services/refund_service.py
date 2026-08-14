from ..extensions import db
from .wallet_service import post, ensure_wallet
from .notification_service import notify


def refund_order(order_id):
    from ..models import Order
    order = db.session.get(Order, order_id)
    if not order or order.status != 'COMPLETED':
        raise ValueError('Faqat completed order refund qilinadi.')
    for item in order.items:
        wallet = ensure_wallet(item.seller.user)
        post(wallet, 'REFUND', item.seller_amount, 'order', order.id, f'Refund reversal for order #{order.order_code}')
        notify(item.seller.user_id, 'Order refunded', f'Order #{order.order_code} qaytarildi.')
    order.status = 'REFUNDED'
    notify(order.buyer_id, 'Refund approved', f'Order #{order.order_code} refund qilindi.')
    return order
