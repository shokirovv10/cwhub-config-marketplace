from datetime import datetime, timedelta
import secrets
import hashlib
from pathlib import Path
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, desc, or_
from ..extensions import db
from ..decorators import admin_required, super_admin_required, finance_admin_required, SCOPE_ENDPOINTS
from ..models import *
from ..services.payment_service import approve_manual, reject_manual
from ..services.wallet_service import release_withdrawal
from ..services.notification_service import notify
from . import bp


def mask_card_number(number):
    digits=''.join(ch for ch in (number or '') if ch.isdigit())
    if len(digits) <= 4: return digits
    return '**** **** **** ' + digits[-4:]

def log(action, target='', details=''):
    db.session.add(AdminActivityLog(
        admin_id=current_user.id,
        action=action,
        target=target,
        ip=request.remote_addr,
        details=details,
    ))


def sidebar_items():
    all_items = [
        {'endpoint':'admin.dashboard','label':'Umumiy ko‘rinish','icon':'⌂','badge':'','kwargs':{}},
        {'endpoint':'admin.configs','label':'Configlar','icon':'▣','badge':Config.query.filter_by(status='PENDING').count() or '','kwargs':{}},
        {'endpoint':'admin.payments','label':'To‘lovlar','icon':'₿','badge':Payment.query.filter_by(status='PENDING').count() or '','kwargs':{}},
        {'endpoint':'admin.orders','label':'Buyurtmalar','icon':'☷','badge':'','kwargs':{}},
        {'endpoint':'admin.withdrawals','label':'Pul yechish','icon':'↗','badge':Withdrawal.query.filter(Withdrawal.status.in_(['PENDING','PROCESSING'])).count() or '','kwargs':{}},
        {'endpoint':'admin.sellers','label':'Sotuvchilar','icon':'@','badge':SellerProfile.query.filter_by(approved=False).count() or '','kwargs':{}},
        {'endpoint':'admin.users','label':'Foydalanuvchilar','icon':'◉','badge':'','kwargs':{}},
        {'endpoint':'admin.catalog','label':'Katalog','icon':'▦','badge':'','kwargs':{}},
        {'endpoint':'admin.settings','label':'Sozlamalar','icon':'⚙','badge':'','kwargs':{}},
        {'endpoint':'admin.activity','label':'Faoliyat tarixi','icon':'◌','badge':'','kwargs':{}},
        {'endpoint':'admin.finance','label':'Foyda / Zarar','icon':'₿','badge':'','kwargs':{}},
        {'endpoint':'admin.announcements','label':'E’lonlar','icon':'!','badge':'','kwargs':{}},
        {'endpoint':'business.admin_plans','label':'Tariflar / to‘lovlar','icon':'₿','badge':SellerSubscription.query.filter_by(status='PAYMENT_SUBMITTED').count() or '','kwargs':{}},
        {'endpoint':'business.admin_support','label':'Yordam markazi','icon':'?','badge':SupportTicket.query.filter_by(status='OPEN').count() or '','kwargs':{}},
        {'endpoint':'admin.admin_applications','label':'Administratorlik arizalari','icon':'★','badge':AdminApplication.query.filter_by(status='PENDING').count() or '','kwargs':{}},
        {'endpoint':'business.admin_reports','label':'Shikoyatlar / xavfsizlik','icon':'!','badge':ConfigReport.query.filter_by(status='PENDING').count() or '','kwargs':{}},
        {'endpoint':'business.admin_referral','label':'Taklif statistikasi','icon':'↗','badge':'','kwargs':{}},
    ]
    if current_user.is_super_admin:
        return all_items
    scope = getattr(current_user, 'admin_scope', None)
    allowed = SCOPE_ENDPOINTS.get(scope, set())
    return [x for x in all_items if x['endpoint'] in allowed]


def render_admin(template, **context):
    return render_template(
        template,
        sidebar_items=sidebar_items(),
        sidebar_kicker='Boshqaruv markazi',
        sidebar_title='CwHUB Admini',
        sidebar_cta={'endpoint':'admin.configs','kwargs':{},'label':'Configlarni tekshirish'},
        **context,
    )

@bp.get('/')
@bp.get('/dashboard')
@login_required
@admin_required
def dashboard():
    completed = Order.query.filter_by(status='COMPLETED')
    revenue = db.session.query(func.coalesce(func.sum(Order.gross_amount), 0)).filter(Order.status == 'COMPLETED').scalar() or 0
    commission = db.session.query(func.coalesce(func.sum(OrderItem.commission_amount), 0)).join(Order).filter(Order.status == 'COMPLETED').scalar() or 0
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).scalar() or 0
    refunds = db.session.query(func.coalesce(func.sum(OrderItem.commission_amount), 0)).join(Order).filter(Order.status == 'REFUNDED').scalar() or 0
    net_profit = Decimal(str(commission)) - Decimal(str(expenses)) - Decimal(str(refunds))
    stats = {
        'users': User.query.count(),
        'sellers': SellerProfile.query.filter_by(approved=True).count(),
        'configs': Config.query.filter(Config.status != 'DELETED').count(),
        'orders': Order.query.count(),
        'revenue': revenue,
        'commission': commission,
        'expenses': expenses,
        'refunds': refunds,
        'net_profit': net_profit,
        'pending_payments': Payment.query.filter_by(status='PENDING').count(),
        'pending_withdrawals': Withdrawal.query.filter(Withdrawal.status.in_(['PENDING','PROCESSING'])).count(),
    }
    start = datetime.utcnow().date() - timedelta(days=13)
    daily = {start + timedelta(days=i): Decimal('0') for i in range(14)}
    for order in completed.order_by(Order.created_at.asc()).all():
        day = order.created_at.date()
        if day in daily:
            daily[day] += Decimal(order.gross_amount)
    chart = [{'label': day.strftime('%d'), 'amount': float(daily[day])} for day in daily]
    return render_admin('admin/dashboard.html', stats=stats, chart=chart)

@bp.get('/configs')
@login_required
@admin_required
def configs():
    q = Config.query
    status = request.args.get('status')
    search = request.args.get('q','').strip()
    if status:
        q = q.filter_by(status=status)
    if search:
        q = q.join(SellerProfile).filter(or_(Config.name.ilike(f'%{search}%'), SellerProfile.nickname.ilike(f'%{search}%')))
    items = q.order_by(Config.created_at.desc()).limit(300).all()
    return render_admin('admin/configs.html', configs=items)

@bp.post('/configs/<int:id>/approve')
@login_required
@admin_required
def approve_config(id):
    config = db.session.get(Config, id)
    if not config: abort(404)
    config.status = 'APPROVED'; config.reject_reason = None
    notify(config.seller.user_id, 'Config approved', 'Sizning configingiz tasdiqlandi va marketplacega chiqdi.')
    log('Approved config', f'Config:{id}')
    db.session.commit(); flash('Config tasdiqlandi.', 'success')
    return redirect(url_for('admin.configs'))

@bp.post('/configs/<int:id>/reject')
@login_required
@admin_required
def reject_config(id):
    config = db.session.get(Config, id)
    if not config: abort(404)
    reason = request.form.get('reason','').strip()
    config.status = 'REJECTED'; config.reject_reason = reason
    notify(config.seller.user_id, 'Config rejected', reason or 'Sabab ko‘rsatilmagan.')
    log('Rejected config', f'Config:{id}', reason)
    db.session.commit(); flash('Config rad etildi.', 'warning')
    return redirect(url_for('admin.configs'))

@bp.post('/configs/<int:id>/hide')
@login_required
@admin_required
def hide_config(id):
    config = db.session.get(Config, id)
    if not config: abort(404)
    config.status = 'HIDDEN'; log('Hidden config', f'Config:{id}'); db.session.commit()
    flash('Config yashirildi.', 'success'); return redirect(url_for('admin.configs'))

@bp.post('/configs/<int:id>/delete')
@login_required
@admin_required
def delete_config(id):
    config = db.session.get(Config, id)
    if not config: abort(404)
    config.status = 'DELETED'; log('Deleted config', f'Config:{id}'); db.session.commit()
    flash('Config marketplace’dan o‘chirildi.', 'success'); return redirect(url_for('admin.configs'))

@bp.get('/payments')
@login_required
@admin_required
def payments():
    items = Payment.query.order_by(Payment.created_at.desc()).limit(300).all()
    return render_admin('admin/payments.html', payments=items)

@bp.get('/payments/<int:id>/receipt')
@login_required
@admin_required
def payment_receipt(id):
    payment=db.session.get(Payment,id)
    if not payment or not payment.receipt:
        return render_template('admin/file_unavailable.html',title='Chek topilmadi',message='Ushbu to‘lov uchun chek fayli topilmadi yoki hali yuklanmagan.'),404
    path=payment.receipt.file_path
    if not path or not Path(path).is_file():
        return render_template('admin/file_unavailable.html',title='Chek mavjud emas',message='Chek yozuvi bazada mavjud, ammo fayl saqlash joyida topilmadi.'),404
    return send_file(path,as_attachment=False,download_name=payment.receipt.original_name,conditional=True)

@bp.post('/payments/<int:id>/approve')
@login_required
@admin_required
def approve_payment(id):
    try:
        approve_manual(id); log('Approved payment', f'Payment:{id}'); db.session.commit(); flash('To‘lov tasdiqlandi.', 'success')
    except ValueError as exc:
        db.session.rollback(); flash(str(exc), 'danger')
    return redirect(url_for('admin.payments'))

@bp.post('/payments/<int:id>/reject')
@login_required
@admin_required
def reject_payment(id):
    try:
        reject_manual(id, request.form.get('reason','')); log('Rejected payment', f'Payment:{id}'); db.session.commit(); flash('To‘lov rad etildi.', 'warning')
    except ValueError as exc:
        db.session.rollback(); flash(str(exc), 'danger')
    return redirect(url_for('admin.payments'))

@bp.get('/sellers/<int:id>/verification')
@login_required
@admin_required
def seller_verification_document(id):
    seller = db.session.get(SellerProfile, id)
    if not seller or not seller.verification_document: abort(404)
    return send_file(seller.verification_document, as_attachment=False, download_name=seller.verification_original_name or 'verification-document', conditional=True)

@bp.post('/sellers/<int:id>/approve')
@login_required
@admin_required
def approve_seller(id):
    seller = db.session.get(SellerProfile, id)
    if not seller: abort(404)
    if not seller.verification_document:
        flash('Verification hujjati topilmadi.', 'danger')
        return redirect(url_for('admin.sellers'))
    seller.approved = True
    seller.verification_status = 'APPROVED'
    seller.verification_reject_reason = None
    seller.verification_reviewed_at = datetime.utcnow()
    seller.verification_reviewed_by = current_user.id
    seller.user.role = 'SELLER'
    seller.user.is_verified = True
    if not seller.user.wallet:
        seller.user.wallet = Wallet()
    notify(seller.user_id, 'Seller verification approved', 'Seller akkauntingiz tasdiqlandi. Endi config sotishingiz mumkin.')
    log('Approved seller verification', f'Seller:{id}')
    db.session.commit()
    flash('Sotuvchi tasdiqlandi.', 'success')
    return redirect(url_for('admin.sellers'))

@bp.post('/sellers/<int:id>/reject')
@login_required
@admin_required
def reject_seller(id):
    seller = db.session.get(SellerProfile, id)
    if not seller: abort(404)
    reason = request.form.get('reason','').strip()
    seller.approved = False
    seller.verification_status = 'REJECTED'
    seller.verification_reject_reason = reason
    seller.verification_reviewed_at = datetime.utcnow()
    seller.verification_reviewed_by = current_user.id
    seller.user.role = 'USER'
    notify(seller.user_id, 'Seller verification rejected', reason or 'Verification hujjati tasdiqlanmadi.')
    log('Rejected seller verification', f'Seller:{id}', reason)
    db.session.commit()
    flash('Sotuvchi verifikatsiyasi rad etildi.', 'warning')
    return redirect(url_for('admin.sellers'))

@bp.get('/withdrawals')
@login_required
@admin_required
def withdrawals():
    items = Withdrawal.query.order_by(Withdrawal.created_at.desc()).limit(300).all()
    return render_admin('admin/withdrawals.html', withdrawals=items)

@bp.post('/withdrawals/<int:id>/process')
@login_required
@finance_admin_required
def process_withdrawal(id):
    withdrawal = db.session.get(Withdrawal, id)
    if not withdrawal or withdrawal.status != 'PENDING': abort(400)
    withdrawal.status = 'PROCESSING'; log('Pul yechish jarayoni boshlandi', f'Withdrawal:{id}'); db.session.commit()
    return redirect(url_for('admin.withdrawals'))

@bp.post('/withdrawals/<int:id>/pay')
@login_required
@super_admin_required
def pay_withdrawal(id):
    withdrawal = db.session.get(Withdrawal, id)
    if not withdrawal or withdrawal.status not in {'PENDING','PROCESSING'}: abort(400)
    withdrawal.status = 'COMPLETED'; withdrawal.processed_at = datetime.utcnow()
    release_withdrawal(withdrawal.seller.user, withdrawal.amount, withdrawal.id, rejected=False)
    notify(withdrawal.seller.user_id, 'Pul yechish yakunlandi', f'{withdrawal.amount} UZS to‘landi.')
    log('Pul yechish to‘landi', f'Withdrawal:{id}')
    db.session.commit(); flash('Pul yechish yakunlandi.', 'success')
    return redirect(url_for('admin.withdrawals'))

@bp.post('/withdrawals/<int:id>/reject')
@login_required
@finance_admin_required
def reject_withdrawal(id):
    withdrawal = db.session.get(Withdrawal, id)
    if not withdrawal or withdrawal.status == 'COMPLETED': abort(400)
    reason = request.form.get('reason','').strip()
    if withdrawal.status in {'PENDING','PROCESSING'}:
        release_withdrawal(withdrawal.seller.user, withdrawal.amount, withdrawal.id, rejected=True)
    withdrawal.status = 'REJECTED'; withdrawal.reject_reason = reason; withdrawal.processed_at = datetime.utcnow()
    notify(withdrawal.seller.user_id, 'Pul yechish rad etildi', reason or 'Sabab ko‘rsatilmagan.')
    log('Pul yechish rad etildi', f'Withdrawal:{id}', reason)
    db.session.commit(); flash('Pul yechish rad etildi.', 'warning')
    return redirect(url_for('admin.withdrawals'))

@bp.get('/sellers')
@login_required
@admin_required
def sellers():
    return render_admin('admin/sellers.html', sellers=SellerProfile.query.order_by(SellerProfile.created_at.desc()).all())

@bp.get('/users')
@login_required
@super_admin_required
def users():
    q = User.query
    search = request.args.get('q','').strip()
    if search:
        q = q.filter(or_(User.username.ilike(f'%{search}%'), User.email.ilike(f'%{search}%')))
    return render_admin('admin/users.html', users=q.order_by(User.created_at.desc()).limit(400).all())

@bp.post('/users/<int:id>/toggle-ban')
@login_required
@super_admin_required
def toggle_ban(id):
    user = db.session.get(User, id)
    if not user: abort(404)
    if user.is_super_admin and not current_user.is_super_admin: abort(403)
    if user.id == current_user.id: flash('O‘zingizni bloklay olmaysiz.', 'warning'); return redirect(url_for('admin.users'))
    user.is_active_user = not user.is_active_user
    log('Toggled ban', f'User:{id}'); db.session.commit(); flash('Foydalanuvchi holati yangilandi.', 'success')
    return redirect(url_for('admin.users'))


@bp.post('/users/<int:id>/verify')
@login_required
@super_admin_required
def verify_user(id):
    user = db.session.get(User, id)
    if not user: abort(404)
    user.is_verified = not user.is_verified
    log('Foydalanuvchi verifikatsiyasi o‘zgartirildi', f'User:{id}', 'verified=' + str(user.is_verified))
    db.session.commit()
    flash('Foydalanuvchi verifikatsiyasi yangilandi.', 'success')
    return redirect(url_for('admin.users'))

@bp.post('/users/<int:id>/role')
@login_required
@super_admin_required
def set_role(id):
    user = db.session.get(User, id)
    role = request.form.get('role','USER')
    if not user or role not in {'USER','SELLER','ADMIN','SUPER_ADMIN'}: abort(400)
    if user.id == current_user.id and role != 'SUPER_ADMIN':
        flash('Super Admin o‘z rolini shu yerda pasaytira olmaydi.', 'warning')
        return redirect(url_for('admin.users'))
    user.role = role
    if role == 'SUPER_ADMIN':
        user.admin_scope = 'SUPER_ADMIN'
    elif role == 'ADMIN':
        if (request.form.get('admin_scope') or '').strip() in {'ADMIN','MODERATOR','SUPPORT','FINANCE'}:
            user.admin_scope = (request.form.get('admin_scope') or '').strip()
        elif not user.admin_scope:
            user.admin_scope = 'ADMIN'
    else:
        user.admin_scope = None
    log('Changed role', f'User:{id}', f'role={role};scope={user.admin_scope}')
    db.session.commit(); flash('Rol yangilandi.', 'success')
    return redirect(url_for('admin.users'))


@bp.post('/users/<int:id>/reset-password')
@login_required
@super_admin_required
def reset_password(id):
    user=db.session.get(User,id)
    if not user: abort(404)
    if user.is_super_admin and user.id != current_user.id: abort(403)
    temp_password = secrets.token_urlsafe(12) + 'A1!'
    expires_at = datetime.utcnow() + timedelta(minutes=2)
    user.set_temporary_password(temp_password, expires_at)
    db.session.add(SecurityEvent(user_id=user.id,event_type='ADMIN_TEMP_PASSWORD_CREATED',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500],details=f'Admin:{current_user.id};expires=120s'))
    db.session.commit()
    return render_template('admin/reset_password_result.html', user=user, temp_password=temp_password, expires_at=expires_at, seconds=120)

@bp.post('/users/<int:id>/delete')
@login_required
@super_admin_required
def delete_user(id):
    user=db.session.get(User,id)
    if not user: abort(404)
    if user.is_super_admin or user.id==current_user.id: abort(403)
    suffix=secrets.token_hex(5)
    user.username=f'o‘chirilgan_{user.id}_{suffix}'[:80]
    user.username_key=user.username.casefold()[:80]
    user.email=f'deleted-{user.id}-{suffix}@invalid.local'
    user.nickname=None; user.description=None; user.avatar=None; user.is_active_user=False; user.is_verified=False; user.role='USER'
    db.session.add(SecurityEvent(user_id=user.id,event_type='ACCOUNT_ANONYMIZED',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500],details=f'Admin:{current_user.id}'))
    db.session.commit(); flash('Foydalanuvchi ma’lumotlari anonimlashtirilib, akkaunt o‘chirildi.', 'success'); return redirect(url_for('admin.users'))

@bp.post('/users/<int:id>/seller-title')
@login_required
@super_admin_required
def seller_title(id):
    user=db.session.get(User,id)
    if not user: abort(404)
    title=request.form.get('title','').strip()
    allowed={'','Yangi sotuvchi','O‘sayotgan sotuvchi','Pro sotuvchi','Top sotuvchi'}
    if title not in allowed: abort(400)
    user.seller_title=title or None
    db.session.commit(); flash('Sotuvchi unvoni yangilandi.', 'success'); return redirect(url_for('admin.users'))

@bp.get('/admin-arizalari')
@login_required
@admin_required
def admin_applications():
    apps=AdminApplication.query.order_by(AdminApplication.created_at.desc()).limit(300).all(); return render_admin('admin/applications.html', applications=apps)

@bp.post('/admin-arizalari/<int:id>/status')
@login_required
@admin_required
def admin_application_status(id):
    app=AdminApplication.query.get_or_404(id); status=request.form.get('status','PENDING')
    if status not in {'PENDING','APPROVED','REJECTED'}: abort(400)
    app.status=status; app.admin_note=(request.form.get('note') or '').strip() or None; app.reviewed_by=current_user.id; app.reviewed_at=datetime.utcnow()
    if status=='APPROVED' and app.desired_role in {'MODERATOR','SUPPORT','FINANCE'}:
        # Map helper role to platform ADMIN while preserving requested specialization in note/title.
        app.user.role='ADMIN'
        app.user.admin_scope=app.desired_role
        log('Administratorlik arizasi tasdiqlandi', f'Application:{id}', f'user={app.user_id};scope={app.desired_role}')
    db.session.commit(); flash('Administratorlik arizasi holati yangilandi.', 'success'); return redirect(url_for('admin.admin_applications'))

@bp.get('/orders')
@login_required
@admin_required
def orders():
    return render_admin('admin/orders.html', orders=Order.query.order_by(Order.created_at.desc()).limit(300).all())

@bp.post('/orders/<int:id>/refund')
@login_required
@admin_required
def refund(id):
    from ..services.refund_service import refund_order
    try:
        refund_order(id); log('Refunded order', f'Order:{id}'); db.session.commit(); flash('Buyurtma puli qaytarildi.', 'success')
    except ValueError as exc:
        db.session.rollback(); flash(str(exc), 'danger')
    return redirect(url_for('admin.orders'))

@bp.get('/catalog')
@login_required
@admin_required
def catalog():
    return render_admin('admin/catalog.html', categories=Category.query.order_by(Category.name).all(), types=ConfigType.query.order_by(ConfigType.name).all(), games=Game.query.order_by(Game.name).all())

@bp.post('/catalog/category')
@login_required
@admin_required
def add_category():
    name = request.form.get('name','').strip(); slug = request.form.get('slug','').strip()
    if not name or not slug or Category.query.filter(or_(Category.name==name, Category.slug==slug)).first():
        flash('Kategoriya ma’lumoti noto‘g‘ri yoki allaqachon mavjud.', 'danger')
    else:
        db.session.add(Category(name=name, slug=slug)); db.session.commit(); flash('Kategoriya qo‘shildi.', 'success')
    return redirect(url_for('admin.catalog'))

@bp.post('/catalog/type')
@login_required
@admin_required
def add_config_type():
    name=request.form.get('name','').strip(); slug=request.form.get('slug','').strip()
    if not name or not slug or ConfigType.query.filter(or_(ConfigType.name==name, ConfigType.slug==slug)).first():
        flash('Config turi noto‘g‘ri yoki allaqachon mavjud.', 'danger')
    else:
        db.session.add(ConfigType(name=name, slug=slug)); db.session.commit(); flash('Config turi qo‘shildi.', 'success')
    return redirect(url_for('admin.catalog'))

@bp.post('/catalog/game')
@login_required
@admin_required
def add_game():
    name = request.form.get('name','').strip(); slug = request.form.get('slug','').strip()
    if not name or not slug or Game.query.filter(or_(Game.name==name, Game.slug==slug)).first():
        flash('O‘yin ma’lumoti noto‘g‘ri yoki allaqachon mavjud.', 'danger')
    else:
        db.session.add(Game(name=name, slug=slug)); db.session.commit(); flash('O‘yin qo‘shildi.', 'success')
    return redirect(url_for('admin.catalog'))

@bp.post('/settings/cards/add')
@login_required
@admin_required
def add_card():
    number = request.form.get('card_number','').strip()
    owner = request.form.get('card_owner','').strip()
    label = request.form.get('label','Main Card').strip() or 'Main Card'
    if not number or not owner:
        flash('Karta raqami va karta egasi majburiy.', 'danger')
    else:
        db.session.add(PaymentCard(card_number=number, card_owner=owner, label=label, enabled=True))
        log('Added payment card', 'PaymentCard')
        db.session.commit()
        flash('Yangi karta qo‘shildi.', 'success')
    return redirect(url_for('admin.settings'))

@bp.post('/settings/cards/<int:id>/toggle')
@login_required
@admin_required
def toggle_card(id):
    card = db.session.get(PaymentCard, id)
    if not card: abort(404)
    card.enabled = not card.enabled
    log('Toggled payment card', f'PaymentCard:{id}')
    db.session.commit()
    flash('Karta holati yangilandi.', 'success')
    return redirect(url_for('admin.settings'))

@bp.post('/settings/cards/<int:id>/delete')
@login_required
@admin_required
def delete_card(id):
    card = db.session.get(PaymentCard, id)
    if not card: abort(404)
    db.session.delete(card)
    log('Deleted payment card', f'PaymentCard:{id}')
    db.session.commit()
    flash('Karta o‘chirildi.', 'success')
    return redirect(url_for('admin.settings'))

@bp.get('/settings')
@login_required
@admin_required
def settings():
    cards = PaymentCard.query.order_by(PaymentCard.created_at.desc()).all()
    for card in cards:
        card.masked_number = mask_card_number(card.card_number)
    return render_admin('admin/settings.html', settings=SiteSettings.get_or_create(), payment=PaymentSettings.get_or_create(), cards=cards)

@bp.post('/settings')
@login_required
@admin_required
def save_settings():
    settings = SiteSettings.get_or_create(); payment = PaymentSettings.get_or_create()
    try:
        settings.commission_rate = Decimal(request.form.get('commission_rate','10'))
        settings.minimum_withdrawal = Decimal(request.form.get('minimum_withdrawal','50000'))
    except Exception:
        flash('Moliyaviy sozlamalar noto‘g‘ri kiritildi.', 'danger'); return redirect(url_for('admin.settings'))
    settings.auto_approve_products = bool(request.form.get('auto_approve_products'))
    settings.seller_registration_auto_approve = False
    settings.maintenance_mode = bool(request.form.get('maintenance_mode'))
    settings.test_mode = bool(request.form.get('test_mode'))
    settings.allowed_extensions = request.form.get('allowed_extensions','cfg,zip,rar,txt')
    payment.manual_enabled = bool(request.form.get('manual_enabled'))
    payment.click_enabled = bool(request.form.get('click_enabled'))
    payment.payme_enabled = bool(request.form.get('payme_enabled'))
    payment.card_number = request.form.get('card_number','').strip()
    payment.card_owner = request.form.get('card_owner','').strip()
    payment.instructions = request.form.get('instructions','').strip()
    log('Sozlamalar yangilandi','Sozlamalar'); db.session.commit(); flash('Sozlamalar saqlandi.', 'success')
    return redirect(url_for('admin.settings'))

@bp.get('/activity')
@login_required
@admin_required
def activity():
    return render_admin('admin/activity.html', logs=AdminActivityLog.query.order_by(AdminActivityLog.created_at.desc()).limit(300).all())


@bp.get('/finance')
@login_required
@admin_required
def finance():
    completed_commission = db.session.query(func.coalesce(func.sum(OrderItem.commission_amount), 0)).join(Order).filter(Order.status == 'COMPLETED').scalar() or 0
    refunded_commission = db.session.query(func.coalesce(func.sum(OrderItem.commission_amount), 0)).join(Order).filter(Order.status == 'REFUNDED').scalar() or 0
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).scalar() or 0
    net_profit = Decimal(str(completed_commission)) - Decimal(str(refunded_commission)) - Decimal(str(expenses))
    recent = Expense.query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(100).all()
    return render_admin('admin/finance.html', commission=Decimal(str(completed_commission)), refunds=Decimal(str(refunded_commission)), expenses=Decimal(str(expenses)), net_profit=net_profit, recent=recent)

@bp.post('/finance/expense')
@login_required
@admin_required
def add_expense():
    title=request.form.get('title','').strip()
    category=request.form.get('category','OTHER').strip() or 'OTHER'
    description=request.form.get('description','').strip()
    try:
        amount=Decimal(request.form.get('amount','0'))
    except Exception:
        amount=Decimal('0')
    if not title or amount <= 0:
        flash('Xarajat nomi va musbat summa kiriting.', 'danger')
        return redirect(url_for('admin.finance'))
    db.session.add(Expense(title=title,amount=amount,category=category,description=description,created_by=current_user.id))
    log('Added expense','Expense',f'{title}: {amount}')
    db.session.commit(); flash('Xarajat qo‘shildi.', 'success')
    return redirect(url_for('admin.finance'))

@bp.post('/finance/expense/<int:id>/delete')
@login_required
@admin_required
def delete_expense(id):
    item=db.session.get(Expense,id)
    if not item: abort(404)
    db.session.delete(item); log('Deleted expense',f'Expense:{id}'); db.session.commit(); flash('Xarajat o‘chirildi.','success')
    return redirect(url_for('admin.finance'))

@bp.route('/announcements', methods=['GET','POST'])
@login_required
@admin_required
def announcements():
    if request.method=='POST':
        title=request.form.get('title','').strip(); message=request.form.get('message','').strip(); level=request.form.get('level','INFO').strip()
        if title and message:
            db.session.add(Announcement(title=title,message=message,level=level if level in {'INFO','SUCCESS','WARNING'} else 'INFO',created_by=current_user.id))
            log('Created announcement','Announcement',title); db.session.commit(); flash('E’lon yaratildi.','success')
        else: flash('Sarlavha va matn majburiy.','danger')
    items=Announcement.query.order_by(Announcement.created_at.desc()).limit(100).all()
    return render_admin('admin/announcements.html', announcements=items)

@bp.post('/announcements/<int:id>/toggle')
@login_required
@admin_required
def toggle_announcement(id):
    item=db.session.get(Announcement,id)
    if not item: abort(404)
    item.enabled=not item.enabled; db.session.commit(); flash('E’lon holati yangilandi.','success')
    return redirect(url_for('admin.announcements'))

@bp.post('/announcements/<int:id>/delete')
@login_required
@admin_required
def delete_announcement(id):
    item=db.session.get(Announcement,id)
    if not item: abort(404)
    db.session.delete(item); db.session.commit(); flash('E’lon o‘chirildi.','success')
    return redirect(url_for('admin.announcements'))
