from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from flask import session
from sqlalchemy import func
from ..extensions import db
from ..models import Config, Order, OrderItem, Payment, Coupon, CouponRedemption, FraudFlag
from .commission_service import split_amount

Q = Decimal('0.01')

def _discount_for_coupon(coupon, gross):
    if coupon.discount_percent:
        discount = gross * Decimal(coupon.discount_percent) / Decimal('100')
    else:
        discount = Decimal(coupon.discount_fixed or 0)
    return max(Decimal('0'), min(gross, discount)).quantize(Q, rounding=ROUND_HALF_UP)

def _coupon_for_order(buyer, configs, gross):
    code = (session.get('coupon_code') or '').strip().upper()
    if not code:
        return None, Decimal('0')
    coupon = Coupon.query.filter_by(code=code, enabled=True).first()
    if not coupon:
        session.pop('coupon_code', None); session.pop('coupon_discount', None)
        return None, Decimal('0')
    if coupon.expires_at and coupon.expires_at < __import__('datetime').datetime.utcnow():
        return None, Decimal('0')
    if coupon.starts_at and coupon.starts_at > __import__('datetime').datetime.utcnow():
        return None, Decimal('0')
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        return None, Decimal('0')
    if CouponRedemption.query.filter_by(coupon_id=coupon.id, user_id=buyer.id).first():
        return None, Decimal('0')
    if gross < Decimal(coupon.min_order or 0):
        return None, Decimal('0')
    if coupon.seller_id and any(c.seller_id != coupon.seller_id for c in configs):
        return None, Decimal('0')
    return coupon, _discount_for_coupon(coupon, gross)

def create_order(buyer, config_ids):
    ids=[]; configs=[]
    for cid in config_ids:
        if int(cid) not in ids: ids.append(int(cid))
    for cid in ids:
        c=db.session.get(Config,cid)
        if c and c.status=='APPROVED' and c.seller and c.seller.user_id!=buyer.id:
            configs.append(c)
    if not configs: raise ValueError('Sotib olish uchun mahsulot topilmadi.')
    gross=sum((Decimal(c.price) for c in configs),Decimal('0.00'))
    from .settings_service import settings
    ss=settings()
    coupon, discount = _coupon_for_order(buyer, configs, gross)
    net_total = gross - discount
    order=Order(order_code=f'CWH{uuid4().hex[:12].upper()}',buyer_id=buyer.id,gross_amount=net_total,discount_amount=discount,coupon_code=(coupon.code if coupon else None),status='PENDING_PAYMENT',idempotency_key=uuid4().hex)
    db.session.add(order); db.session.flush()
    remaining_discount = discount
    for index, c in enumerate(configs):
        original=Decimal(c.price)
        if index == len(configs)-1:
            item_discount = remaining_discount
        else:
            item_discount = (discount * original / gross).quantize(Q, rounding=ROUND_HALF_UP) if gross else Decimal('0')
            item_discount=min(item_discount, remaining_discount)
        remaining_discount -= item_discount
        net=original-item_discount
        from ..models import SellerSubscription
        sub = SellerSubscription.query.filter_by(seller_id=c.seller_id, status='ACTIVE').order_by(SellerSubscription.created_at.desc()).first()
        commission_rate = sub.plan.commission_rate if sub and (not sub.expires_at or sub.expires_at >= __import__('datetime').datetime.utcnow()) else ss.commission_rate
        comm,seller=split_amount(net,commission_rate)
        db.session.add(OrderItem(order_id=order.id,config_id=c.id,seller_id=c.seller_id,unit_price=original,net_amount=net,commission_rate=commission_rate,commission_amount=comm,seller_amount=seller))
    if coupon:
        db.session.add(CouponRedemption(coupon_id=coupon.id,user_id=buyer.id,order_id=order.id,discount_amount=discount))
        coupon.used_count += 1
        session.pop('coupon_code',None); session.pop('coupon_discount',None)
    # Basic anti-fraud signal: repeated orders in a short window.
    recent = Order.query.filter(Order.buyer_id==buyer.id, Order.created_at >= __import__('datetime').datetime.utcnow()-__import__('datetime').timedelta(minutes=10)).count()
    if recent >= 5:
        db.session.add(FraudFlag(user_id=buyer.id,kind='RAPID_ORDERS',severity='MEDIUM',reference_type='ORDER',reference_id=str(order.id),details='10 daqiqada ko‘p buyurtma yaratildi.'))
    db.session.add(Payment(order_id=order.id,method='manual',amount=net_total,status='PENDING'))
    db.session.commit(); return order
