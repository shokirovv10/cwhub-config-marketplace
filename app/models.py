from datetime import datetime
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

class User(UserMixin,db.Model):
    id=db.Column(db.Integer,primary_key=True)
    username=db.Column(db.String(80),unique=True,nullable=False,index=True)
    username_key=db.Column(db.String(80),unique=True,nullable=False,index=True)
    email=db.Column(db.String(255),unique=True,nullable=False,index=True)
    description=db.Column(db.Text,nullable=True)
    nickname=db.Column(db.String(120),nullable=True)
    seller_title=db.Column(db.String(60),nullable=True)
    password_hash=db.Column(db.String(255),nullable=False)
    role=db.Column(db.String(20),default='USER',nullable=False,index=True)
    admin_scope=db.Column(db.String(30),nullable=True,index=True)
    temporary_password_expires_at=db.Column(db.DateTime,nullable=True)
    force_password_change=db.Column(db.Boolean,default=False,nullable=False)
    avatar=db.Column(db.String(255)); is_active_user=db.Column(db.Boolean,default=True,nullable=False); is_verified=db.Column(db.Boolean,default=False,nullable=False,index=True); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    seller_profile=db.relationship('SellerProfile',back_populates='user',foreign_keys='SellerProfile.user_id',uselist=False,cascade='all,delete-orphan')
    wallet=db.relationship('Wallet',back_populates='user',uselist=False,cascade='all,delete-orphan')
    cart_items=db.relationship('CartItem',back_populates='user',cascade='all,delete-orphan')
    def set_password(self,p):
        self.password_hash=generate_password_hash(p)
        self.temporary_password_expires_at=None
        self.force_password_change=False
    def set_temporary_password(self,p,expires_at):
        self.password_hash=generate_password_hash(p)
        self.temporary_password_expires_at=expires_at
        self.force_password_change=True
    def set_username(self, value):
        clean = (value or '').strip().lstrip('@')
        self.username = clean
        self.username_key = clean.casefold()
    def check_password(self,p):
        if self.temporary_password_expires_at and self.temporary_password_expires_at < datetime.utcnow():
            return False
        return check_password_hash(self.password_hash,p)
    @property
    def is_banned(self): return not self.is_active_user
    @property
    def is_admin(self): return self.role in {'ADMIN','SUPER_ADMIN'}
    @property
    def is_super_admin(self): return self.role=='SUPER_ADMIN'

class SellerProfile(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),unique=True,nullable=False)
    nickname=db.Column(db.String(100),nullable=False,index=True); description=db.Column(db.Text); payout_info=db.Column(db.Text)
    approved=db.Column(db.Boolean,default=False,nullable=False,index=True); verification_status=db.Column(db.String(20),default='PENDING',nullable=False,index=True); verification_document=db.Column(db.String(600)); verification_original_name=db.Column(db.String(255)); verification_reject_reason=db.Column(db.Text); verification_submitted_at=db.Column(db.DateTime); verification_reviewed_at=db.Column(db.DateTime); verification_reviewed_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True); verification_document_sha256=db.Column(db.String(64)); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User',back_populates='seller_profile',foreign_keys=[user_id]); reviewer=db.relationship('User',foreign_keys=[verification_reviewed_by]); configs=db.relationship('Config',back_populates='seller',cascade='all,delete-orphan'); payout_accounts=db.relationship('SellerPayoutAccount',back_populates='seller',cascade='all,delete-orphan')

class SellerPayoutAccount(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=False,index=True)
    method=db.Column(db.String(40),nullable=False,default='Karta')
    label=db.Column(db.String(80),nullable=False,default='Asosiy hisob')
    destination=db.Column(db.String(255),nullable=False)
    is_default=db.Column(db.Boolean,default=False,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    seller=db.relationship('SellerProfile',back_populates='payout_accounts')

class CartItem(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User',back_populates='cart_items')
    config=db.relationship('Config')
    __table_args__=(db.UniqueConstraint('user_id','config_id',name='uq_cart_user_config'),)

class Category(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(80),unique=True,nullable=False); slug=db.Column(db.String(100),unique=True,nullable=False)
class Game(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(80),unique=True,nullable=False); slug=db.Column(db.String(100),unique=True,nullable=False)

class ConfigType(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(80),unique=True,nullable=False)
    slug=db.Column(db.String(100),unique=True,nullable=False)

class Config(db.Model):
    id=db.Column(db.Integer,primary_key=True); seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=False,index=True)
    category_id=db.Column(db.Integer,db.ForeignKey('category.id'),nullable=False,index=True); type_id=db.Column(db.Integer,db.ForeignKey('config_type.id'),nullable=True,index=True); game_id=db.Column(db.Integer,db.ForeignKey('game.id'),nullable=False,index=True)
    name=db.Column(db.String(180),nullable=False); slug=db.Column(db.String(220),unique=True,nullable=False,index=True); short_description=db.Column(db.String(300)); description=db.Column(db.Text,nullable=True)
    version=db.Column(db.String(80)); price=db.Column(db.Numeric(14,2),nullable=False); tags=db.Column(db.String(500)); main_image=db.Column(db.String(255)); preview_images=db.Column(db.Text)
    file_path=db.Column(db.String(600),nullable=False); file_original_name=db.Column(db.String(255),nullable=False); file_size=db.Column(db.BigInteger,nullable=False); file_mime=db.Column(db.String(150)); demo_url=db.Column(db.String(500))
    status=db.Column(db.String(20),default='PENDING',nullable=False,index=True); reject_reason=db.Column(db.Text); view_count=db.Column(db.Integer,default=0,nullable=False); download_count=db.Column(db.Integer,default=0,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    seller=db.relationship('SellerProfile',back_populates='configs'); category=db.relationship('Category'); config_type=db.relationship('ConfigType'); game=db.relationship('Game'); reviews=db.relationship('Review',back_populates='config',cascade='all,delete-orphan')

class Order(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_code=db.Column(db.String(32),unique=True,nullable=False,index=True); buyer_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    gross_amount=db.Column(db.Numeric(14,2),nullable=False); status=db.Column(db.String(25),default='PENDING_PAYMENT',nullable=False,index=True); idempotency_key=db.Column(db.String(80),unique=True,nullable=False)
    discount_amount=db.Column(db.Numeric(14,2),default=0,nullable=False); coupon_code=db.Column(db.String(80),nullable=True,index=True); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False); buyer=db.relationship('User'); items=db.relationship('OrderItem',back_populates='order',cascade='all,delete-orphan'); payment=db.relationship('Payment',back_populates='order',uselist=False,cascade='all,delete-orphan')
class OrderItem(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey('order.id'),nullable=False,index=True); config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True); seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=False,index=True)
    unit_price=db.Column(db.Numeric(14,2),nullable=False); net_amount=db.Column(db.Numeric(14,2),nullable=False,default=0); commission_rate=db.Column(db.Numeric(5,2),nullable=False); commission_amount=db.Column(db.Numeric(14,2),nullable=False); seller_amount=db.Column(db.Numeric(14,2),nullable=False)
    order=db.relationship('Order',back_populates='items'); config=db.relationship('Config'); seller=db.relationship('SellerProfile'); __table_args__=(db.UniqueConstraint('order_id','config_id',name='uq_order_config'),)
class Payment(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey('order.id'),unique=True,nullable=False); method=db.Column(db.String(30),nullable=False); amount=db.Column(db.Numeric(14,2),nullable=False)
    status=db.Column(db.String(20),default='PENDING',nullable=False,index=True); provider_reference=db.Column(db.String(120),unique=True); approved_at=db.Column(db.DateTime); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    order=db.relationship('Order',back_populates='payment'); receipt=db.relationship('PaymentReceipt',back_populates='payment',uselist=False,cascade='all,delete-orphan')
class PaymentReceipt(db.Model):
    id=db.Column(db.Integer,primary_key=True); payment_id=db.Column(db.Integer,db.ForeignKey('payment.id'),unique=True,nullable=False); file_path=db.Column(db.String(600),nullable=False); original_name=db.Column(db.String(255),nullable=False); sha256=db.Column(db.String(64),index=True); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False); payment=db.relationship('Payment',back_populates='receipt')

class Wallet(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),unique=True,nullable=False); available_balance=db.Column(db.Numeric(14,2),default=0,nullable=False); pending_balance=db.Column(db.Numeric(14,2),default=0,nullable=False); total_earned=db.Column(db.Numeric(14,2),default=0,nullable=False)
    user=db.relationship('User',back_populates='wallet'); transactions=db.relationship('WalletTransaction',back_populates='wallet',cascade='all,delete-orphan')
class WalletTransaction(db.Model):
    id=db.Column(db.Integer,primary_key=True); wallet_id=db.Column(db.Integer,db.ForeignKey('wallet.id'),nullable=False,index=True); tx_type=db.Column(db.String(40),nullable=False); amount=db.Column(db.Numeric(14,2),nullable=False); reference_type=db.Column(db.String(50)); reference_id=db.Column(db.String(80)); description=db.Column(db.String(500)); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    wallet=db.relationship('Wallet',back_populates='transactions')
class Withdrawal(db.Model):
    id=db.Column(db.Integer,primary_key=True); seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=False,index=True); amount=db.Column(db.Numeric(14,2),nullable=False); method=db.Column(db.String(50),nullable=False); payout_destination=db.Column(db.String(255),nullable=False); comment=db.Column(db.String(500)); status=db.Column(db.String(30),default='PENDING',nullable=False,index=True); reject_reason=db.Column(db.Text); processed_at=db.Column(db.DateTime); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False); seller=db.relationship('SellerProfile')
class Review(db.Model):
    id=db.Column(db.Integer,primary_key=True); config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False); rating=db.Column(db.Integer,nullable=False); comment=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False); config=db.relationship('Config',back_populates='reviews'); user=db.relationship('User'); __table_args__=(db.UniqueConstraint('config_id','user_id',name='uq_review_buyer'),)
class Download(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True); config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True); order_id=db.Column(db.Integer,db.ForeignKey('order.id'),nullable=False); ip=db.Column(db.String(64)); timestamp=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
class Notification(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True); title=db.Column(db.String(160),nullable=False); message=db.Column(db.String(500),nullable=False); is_read=db.Column(db.Boolean,default=False,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
class AdminActivityLog(db.Model):
    id=db.Column(db.Integer,primary_key=True); admin_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False); action=db.Column(db.String(160),nullable=False); target=db.Column(db.String(160)); ip=db.Column(db.String(64)); details=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
class SiteSettings(db.Model):
    id=db.Column(db.Integer,primary_key=True); site_name=db.Column(db.String(120),default='CwHUB Config Marketplace'); currency=db.Column(db.String(10),default='UZS'); commission_rate=db.Column(db.Numeric(5,2),default=10); minimum_withdrawal=db.Column(db.Numeric(14,2),default=50000); auto_approve_products=db.Column(db.Boolean,default=False); seller_registration_auto_approve=db.Column(db.Boolean,default=False); maintenance_mode=db.Column(db.Boolean,default=False); test_mode=db.Column(db.Boolean,default=False); max_upload_size=db.Column(db.BigInteger,default=33554432); allowed_extensions=db.Column(db.String(500),default='cfg,zip,rar,txt'); created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    @classmethod
    def get_or_create(cls):
        x=cls.query.first()
        if not x: x=cls(); db.session.add(x); db.session.commit()
        return x
class PaymentCard(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    card_number=db.Column(db.String(50),nullable=False)
    card_owner=db.Column(db.String(120),nullable=False)
    label=db.Column(db.String(80),default='Main Card')
    enabled=db.Column(db.Boolean,default=True,nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)

class PaymentSettings(db.Model):
    id=db.Column(db.Integer,primary_key=True); manual_enabled=db.Column(db.Boolean,default=True); click_enabled=db.Column(db.Boolean,default=False); payme_enabled=db.Column(db.Boolean,default=False); card_number=db.Column(db.String(50)); card_owner=db.Column(db.String(120)); instructions=db.Column(db.Text,default="To'lovni ko'rsatilgan karta orqali amalga oshiring va chekni yuklang.")
    @classmethod
    def get_or_create(cls):
        x=cls.query.first()
        if not x: x=cls(); db.session.add(x); db.session.commit()
        return x


class Wishlist(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')
    config=db.relationship('Config')
    __table_args__=(db.UniqueConstraint('user_id','config_id',name='uq_wishlist_user_config'),)

class Expense(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(160),nullable=False)
    amount=db.Column(db.Numeric(14,2),nullable=False)
    category=db.Column(db.String(80),nullable=False,default='OTHER')
    description=db.Column(db.Text)
    expense_date=db.Column(db.Date,default=lambda: datetime.utcnow().date(),nullable=False,index=True)
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    creator=db.relationship('User')

class Announcement(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(180),nullable=False)
    message=db.Column(db.String(700),nullable=False)
    level=db.Column(db.String(20),default='INFO',nullable=False)
    enabled=db.Column(db.Boolean,default=True,nullable=False,index=True)
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    creator=db.relationship('User')


class SellerPlan(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(80),unique=True,nullable=False)
    slug=db.Column(db.String(100),unique=True,nullable=False)
    monthly_price=db.Column(db.Numeric(14,2),nullable=False,default=0)
    commission_rate=db.Column(db.Numeric(5,2),nullable=False,default=10)
    product_limit=db.Column(db.Integer,nullable=False,default=5)
    highlighted=db.Column(db.Boolean,default=False,nullable=False)
    priority_moderation=db.Column(db.Boolean,default=False,nullable=False)
    description=db.Column(db.Text)
    enabled=db.Column(db.Boolean,default=True,nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)

class SellerSubscription(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=False,index=True)
    plan_id=db.Column(db.Integer,db.ForeignKey('seller_plan.id'),nullable=False,index=True)
    price=db.Column(db.Numeric(14,2),nullable=False,default=0)
    status=db.Column(db.String(20),default='PENDING',nullable=False,index=True)
    started_at=db.Column(db.DateTime)
    expires_at=db.Column(db.DateTime)
    note=db.Column(db.String(500))
    receipt_path=db.Column(db.String(600))
    receipt_original_name=db.Column(db.String(255))
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    seller=db.relationship('SellerProfile')
    plan=db.relationship('SellerPlan')

class Coupon(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    code=db.Column(db.String(60),unique=True,nullable=False,index=True)
    seller_id=db.Column(db.Integer,db.ForeignKey('seller_profile.id'),nullable=True,index=True)
    discount_percent=db.Column(db.Numeric(5,2),default=0,nullable=False)
    discount_fixed=db.Column(db.Numeric(14,2),default=0,nullable=False)
    min_order=db.Column(db.Numeric(14,2),default=0,nullable=False)
    max_uses=db.Column(db.Integer)
    used_count=db.Column(db.Integer,default=0,nullable=False)
    starts_at=db.Column(db.DateTime)
    expires_at=db.Column(db.DateTime)
    enabled=db.Column(db.Boolean,default=True,nullable=False,index=True)
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    seller=db.relationship('SellerProfile')

class CouponRedemption(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    coupon_id=db.Column(db.Integer,db.ForeignKey('coupon.id'),nullable=False,index=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    order_id=db.Column(db.Integer,db.ForeignKey('order.id'),nullable=False,index=True)
    discount_amount=db.Column(db.Numeric(14,2),nullable=False,default=0)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    __table_args__=(db.UniqueConstraint('coupon_id','user_id',name='uq_coupon_user'),)
    coupon=db.relationship('Coupon'); user=db.relationship('User'); order=db.relationship('Order')

class ConfigVersion(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True)
    version_label=db.Column(db.String(80),nullable=False)
    file_path=db.Column(db.String(600),nullable=False)
    file_original_name=db.Column(db.String(255),nullable=False)
    file_size=db.Column(db.BigInteger,nullable=False)
    changelog=db.Column(db.Text)
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    config=db.relationship('Config')

class SupportTicket(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    subject=db.Column(db.String(180),nullable=False)
    category=db.Column(db.String(60),default='OTHER',nullable=False)
    priority=db.Column(db.String(20),default='NORMAL',nullable=False)
    status=db.Column(db.String(20),default='OPEN',nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')
    messages=db.relationship('SupportMessage',back_populates='ticket',cascade='all,delete-orphan',order_by='SupportMessage.created_at')

class SupportMessage(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    ticket_id=db.Column(db.Integer,db.ForeignKey('support_ticket.id'),nullable=False,index=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    message=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    ticket=db.relationship('SupportTicket',back_populates='messages'); user=db.relationship('User')

class PasswordResetToken(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    token_hash=db.Column(db.String(128),unique=True,nullable=False,index=True)
    expires_at=db.Column(db.DateTime,nullable=False,index=True)
    used_at=db.Column(db.DateTime)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')

class AdminApplication(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    desired_role=db.Column(db.String(40),nullable=False,default='MODERATOR')
    experience=db.Column(db.Text,nullable=False)
    motivation=db.Column(db.Text,nullable=False)
    availability=db.Column(db.String(80),nullable=False)
    status=db.Column(db.String(20),nullable=False,default='PENDING',index=True)
    admin_note=db.Column(db.Text)
    reviewed_by=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True)
    reviewed_at=db.Column(db.DateTime)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User',foreign_keys=[user_id])
    reviewer=db.relationship('User',foreign_keys=[reviewed_by])

class ConfigReport(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    config_id=db.Column(db.Integer,db.ForeignKey('config.id'),nullable=False,index=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    reason=db.Column(db.String(120),nullable=False)
    details=db.Column(db.Text)
    status=db.Column(db.String(20),default='PENDING',nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    config=db.relationship('Config'); user=db.relationship('User')

class FraudFlag(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True,index=True)
    kind=db.Column(db.String(80),nullable=False,index=True)
    severity=db.Column(db.String(20),default='LOW',nullable=False)
    reference_type=db.Column(db.String(60)); reference_id=db.Column(db.String(100))
    details=db.Column(db.Text)
    status=db.Column(db.String(20),default='OPEN',nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')

class SecurityEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True,index=True)
    event_type=db.Column(db.String(80),nullable=False,index=True)
    ip=db.Column(db.String(64)); user_agent=db.Column(db.String(500)); details=db.Column(db.Text)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')

class ReferralCode(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,unique=True)
    code=db.Column(db.String(60),unique=True,nullable=False,index=True)
    clicks=db.Column(db.Integer,default=0,nullable=False)
    signups=db.Column(db.Integer,default=0,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    user=db.relationship('User')

class ReferralAttribution(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    referrer_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    referred_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True,unique=True)
    code=db.Column(db.String(60),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
