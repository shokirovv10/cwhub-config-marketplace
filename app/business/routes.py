from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from flask import render_template, request, redirect, url_for, flash, abort, session
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from ..extensions import db
from ..models import (SellerPlan, SellerSubscription, Coupon, CouponRedemption,
    ConfigVersion, SupportTicket, SupportMessage, ConfigReport, FraudFlag,
    SecurityEvent, ReferralCode, ReferralAttribution, Config, SellerProfile, User, SiteSettings, PaymentCard)
from ..decorators import admin_required
from ..services.notification_service import notify
from ..services.storage_service import storage
from . import bp


def _now(): return datetime.utcnow()

@bp.get('/tariflar')
def plans():
    items = SellerPlan.query.filter_by(enabled=True).order_by(SellerPlan.monthly_price.asc()).all()
    return render_template('business/plans.html', plans=items)

@bp.get('/tariflar/<slug>')
def plan_detail(slug):
    plan=SellerPlan.query.filter_by(slug=slug,enabled=True).first_or_404()
    return render_template('business/plan_detail.html', plan=plan)

@bp.post('/sotuvchi/tariflar/<int:plan_id>')
@login_required
def request_plan(plan_id):
    if not (current_user.seller_profile and current_user.seller_profile.approved) and not current_user.is_super_admin:
        flash('Avval sotuvchi sifatida tasdiqlanishingiz kerak.', 'warning')
        return redirect(url_for('seller.apply'))
    plan = db.session.get(SellerPlan, plan_id)
    if not plan or not plan.enabled:
        abort(404)
    seller_id = current_user.seller_profile.id if current_user.seller_profile else None
    if not seller_id:
        abort(403)
    active = SellerSubscription.query.filter_by(seller_id=seller_id, status='ACTIVE').first()
    if active and active.plan_id == plan.id:
        flash('Siz ushbu tarifdan allaqachon foydalanmoqdasiz.', 'info')
        return redirect(url_for('business.seller_plans'))
    if Decimal(plan.monthly_price or 0) <= 0:
        SellerSubscription.query.filter_by(seller_id=seller_id, status='ACTIVE').update({'status':'EXPIRED'})
        sub = SellerSubscription(seller_id=seller_id, plan_id=plan.id, price=plan.monthly_price, status='ACTIVE', started_at=_now(), expires_at=_now()+timedelta(days=30))
        db.session.add(sub); db.session.commit()
        flash('Bepul tarif faollashtirildi.', 'success')
        return redirect(url_for('business.seller_plans'))
    return redirect(url_for('business.plan_payment', plan_id=plan.id))

@bp.get('/sotuvchi/tariflar/<int:plan_id>/tolov')
@login_required
def plan_payment(plan_id):
    if not (current_user.seller_profile and current_user.seller_profile.approved) and not current_user.is_super_admin:
        flash('Avval sotuvchi sifatida tasdiqlanishingiz kerak.', 'warning')
        return redirect(url_for('seller.apply'))
    plan = db.session.get(SellerPlan, plan_id)
    if not plan or not plan.enabled:
        abort(404)
    if Decimal(plan.monthly_price or 0) <= 0:
        return redirect(url_for('business.request_plan', plan_id=plan.id), code=307)
    cards = PaymentCard.query.filter_by(enabled=True).order_by(PaymentCard.created_at.asc()).all()
    return render_template('business/plan_payment.html', plan=plan, cards=cards, instructions=SiteSettings.get_or_create().payment_instructions if hasattr(SiteSettings,'payment_instructions') else None)

@bp.post('/sotuvchi/tariflar/<int:plan_id>/tolov')
@login_required
def plan_payment_submit(plan_id):
    if not (current_user.seller_profile and current_user.seller_profile.approved) and not current_user.is_super_admin:
        abort(403)
    plan = db.session.get(SellerPlan, plan_id)
    if not plan or not plan.enabled:
        abort(404)
    seller_id = current_user.seller_profile.id if current_user.seller_profile else None
    if not seller_id:
        abort(403)
    if Decimal(plan.monthly_price or 0) <= 0:
        return redirect(url_for('business.request_plan', plan_id=plan.id), code=307)
    receipt = request.files.get('receipt')
    receipt_token = request.form.get('receipt_token','').strip()
    if (not receipt or not receipt.filename) and not receipt_token:
        flash('Tarif to‘lovi uchun chekni yuklang.', 'danger')
        return redirect(url_for('business.plan_payment', plan_id=plan.id))
    # Prevent duplicate pending payment requests for same seller+plan.
    existing = SellerSubscription.query.filter_by(seller_id=seller_id, plan_id=plan.id, status='PAYMENT_SUBMITTED').first()
    if existing:
        flash('Ushbu tarif uchun tekshirilayotgan to‘lovingiz allaqachon mavjud.', 'info')
        return redirect(url_for('business.seller_plans'))
    receipt_path = None; receipt_original = None
    try:
        if receipt_token:
            receipt_path, receipt_original, _ = storage().consume_temp(receipt_token, current_user.id, 'plan_receipts')
        else:
            from hashlib import sha256
            safe_name = receipt.filename
            if '.' not in safe_name or safe_name.rsplit('.',1)[-1].lower() not in {'png','jpg','jpeg','webp','pdf'}:
                flash('Chek formati ruxsat etilmagan.', 'danger')
                return redirect(url_for('business.plan_payment', plan_id=plan.id))
            receipt_path, receipt_original, _ = storage().save(receipt, 'plan_receipts', safe_name)
        sub = SellerSubscription(seller_id=seller_id, plan_id=plan.id, price=plan.monthly_price, status='PAYMENT_SUBMITTED', note='Tarif to‘lovi cheki: ' + (receipt_original or ''))
        # store receipt path/name in note-compatible fields via new columns when available; set dynamically for backward compatibility
        if hasattr(sub, 'receipt_path'):
            sub.receipt_path = receipt_path
            sub.receipt_original_name = receipt_original
        db.session.add(sub); db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Tarif to‘lovi yuborilmadi: {exc}', 'danger')
        return redirect(url_for('business.plan_payment', plan_id=plan.id))
    flash('Tarif to‘lovi yuborildi. Administrator chekni tekshiradi.', 'success')
    return redirect(url_for('business.seller_plans'))

@bp.get('/sotuvchi/tariflar')

@login_required

def seller_plans():
    plans = SellerPlan.query.filter_by(enabled=True).order_by(SellerPlan.monthly_price.asc()).all()
    active = None
    history=[]
    if current_user.seller_profile:
        active=SellerSubscription.query.filter_by(seller_id=current_user.seller_profile.id,status='ACTIVE').first()
        history=SellerSubscription.query.filter_by(seller_id=current_user.seller_profile.id).order_by(SellerSubscription.created_at.desc()).limit(20).all()
    return render_template('business/seller_plans.html', plans=plans, active=active, history=history)

@bp.route('/sotuvchi/couponlar', methods=['GET','POST'])
@login_required

def seller_coupons():
    sp=current_user.seller_profile
    if not sp and not current_user.is_super_admin: abort(403)
    if request.method=='POST':
        code=request.form.get('code','').strip().upper()
        try: percent=Decimal(request.form.get('percent','0') or 0)
        except Exception: percent=Decimal('0')
        try: fixed=Decimal(request.form.get('fixed','0') or 0)
        except Exception: fixed=Decimal('0')
        try: min_order=Decimal(request.form.get('min_order','0') or 0)
        except Exception: min_order=Decimal('0')
        try: max_uses=int(request.form['max_uses']) if request.form.get('max_uses') else None
        except Exception: max_uses=None
        if not code or len(code)<3 or len(code)>60:
            flash('Kupon kodi noto‘g‘ri.', 'danger')
        elif percent < 0 or percent > 100 or fixed < 0:
            flash('Chegirma qiymati noto‘g‘ri.', 'danger')
        elif percent and fixed:
            flash('Foizli yoki qat’iy chegirmadan bittasini tanlang.', 'danger')
        elif Coupon.query.filter_by(code=code).first():
            flash('Bu kupon kodi band.', 'danger')
        else:
            db.session.add(Coupon(code=code,seller_id=(sp.id if sp else None),discount_percent=percent,discount_fixed=fixed,min_order=min_order,max_uses=max_uses,created_by=current_user.id,enabled=True))
            db.session.commit(); flash('Kupon yaratildi.', 'success'); return redirect(url_for('business.seller_coupons'))
    coupons=Coupon.query.filter_by(seller_id=(sp.id if sp else None)).order_by(Coupon.created_at.desc()).all() if sp else Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('business/coupons.html', coupons=coupons)

@bp.post('/coupon/tekshir')
@login_required

def validate_coupon():
    code=request.form.get('code','').strip().upper(); total=Decimal(request.form.get('total','0') or 0)
    coupon=Coupon.query.filter_by(code=code,enabled=True).first()
    if not coupon: flash('Kupon topilmadi yoki faol emas.', 'danger'); return redirect(url_for('marketplace.cart'))
    now=_now()
    if coupon.starts_at and now < coupon.starts_at or coupon.expires_at and now > coupon.expires_at: flash('Kupon muddati tugagan.', 'danger'); return redirect(url_for('marketplace.cart'))
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses: flash('Kupon limiti tugagan.', 'danger'); return redirect(url_for('marketplace.cart'))
    if total < coupon.min_order: flash(f'Minimal buyurtma: {coupon.min_order} UZS.', 'danger'); return redirect(url_for('marketplace.cart'))
    discount = (total * coupon.discount_percent / Decimal('100')) if coupon.discount_percent else coupon.discount_fixed
    discount=min(discount,total)
    session['coupon_code']=coupon.code; session['coupon_discount']=str(discount)
    flash(f'Kupon qabul qilindi: -{discount} UZS.', 'success')
    return redirect(url_for('marketplace.cart'))

@bp.post('/coupon/olib-tashlash')
@login_required

def remove_coupon():
    session.pop('coupon_code',None); session.pop('coupon_discount',None); flash('Kupon olib tashlandi.','info'); return redirect(url_for('marketplace.cart'))

@bp.get('/support/ticket/<int:id>')
@login_required

def ticket_detail(id):
    ticket=SupportTicket.query.filter_by(id=id).first_or_404()
    if ticket.user_id != current_user.id and not current_user.is_admin: abort(403)
    return render_template('business/ticket.html', ticket=ticket)

@bp.get('/support/ticketlar')
@login_required

def tickets():
    items=SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.updated_at.desc()).all()
    return render_template('business/tickets.html', tickets=items)

@bp.post('/support/ticket')
@login_required

def create_ticket():
    subject=request.form.get('subject','').strip(); message=request.form.get('message','').strip(); category=request.form.get('category','OTHER').strip()
    if len(subject)<4 or len(message)<5: flash('Mavzu va xabarni to‘liq kiriting.', 'danger'); return redirect(url_for('business.tickets'))
    ticket=SupportTicket(user_id=current_user.id,subject=subject,category=category,priority='NORMAL',status='OPEN')
    db.session.add(ticket); db.session.flush(); db.session.add(SupportMessage(ticket_id=ticket.id,user_id=current_user.id,message=message)); db.session.commit()
    flash(f'Yordam bileti #{ticket.id} yaratildi.','success'); return redirect(url_for('business.ticket_detail',id=ticket.id))

@bp.post('/support/ticket/<int:id>/reply')
@login_required

def ticket_reply(id):
    ticket=SupportTicket.query.get_or_404(id)
    if ticket.user_id != current_user.id and not current_user.is_admin: abort(403)
    msg=request.form.get('message','').strip()
    if len(msg)<2: flash('Xabar juda qisqa.','danger'); return redirect(url_for('business.ticket_detail',id=id))
    db.session.add(SupportMessage(ticket_id=id,user_id=current_user.id,message=msg)); ticket.updated_at=_now(); ticket.status='OPEN' if not current_user.is_admin else 'PENDING_USER'; db.session.commit()
    if current_user.is_admin: notify(ticket.user_id,'Yordam biletingizga javob berildi',f'#{ticket.id} ticketga yangi javob keldi.')
    return redirect(url_for('business.ticket_detail',id=id))

@bp.post('/config/<int:id>/report')
@login_required

def report_config(id):
    config=Config.query.get_or_404(id); reason=request.form.get('reason','').strip(); details=request.form.get('details','').strip()
    if not reason: flash('Sababni tanlang.','danger'); return redirect(request.referrer or url_for('marketplace.config_detail',slug=config.slug))
    existing=ConfigReport.query.filter_by(config_id=id,user_id=current_user.id,status='PENDING').first()
    if existing: flash('Bu config haqida faol shikoyatingiz bor.','info'); return redirect(request.referrer or url_for('marketplace.config_detail',slug=config.slug))
    db.session.add(ConfigReport(config_id=id,user_id=current_user.id,reason=reason,details=details)); db.session.commit(); flash('Shikoyat yuborildi.','success'); return redirect(request.referrer or url_for('marketplace.config_detail',slug=config.slug))

@bp.get('/ref/<code>')
def referral(code):
    from flask import make_response
    ref=ReferralCode.query.filter_by(code=code.strip().upper()).first_or_404(); ref.clicks += 1; db.session.commit()
    resp=make_response(redirect(url_for('main.index'))); resp.set_cookie('cwhub_ref', ref.code, max_age=60*60*24*30, httponly=True, samesite='Lax'); return resp

@bp.get('/referral')
@login_required

def referral_panel():
    ref=ReferralCode.query.filter_by(user_id=current_user.id).first()
    if not ref:
        ref=ReferralCode(user_id=current_user.id,code='CWH-'+current_user.username[:20].upper()+'-'+uuid4().hex[:6].upper()); db.session.add(ref); db.session.commit()
    return render_template('business/referral.html', referral=ref)

# Admin pages
@bp.get('/admin/tariflar')
@login_required
@admin_required

def admin_plans():
    plans=SellerPlan.query.order_by(SellerPlan.monthly_price.asc()).all(); subs=SellerSubscription.query.order_by(SellerSubscription.created_at.desc()).limit(200).all()
    return render_template('business/admin_plans.html', plans=plans, subscriptions=subs)

@bp.post('/admin/tariflar')
@login_required
@admin_required

def admin_plan_create():
    name=request.form.get('name','').strip(); slug=request.form.get('slug','').strip().lower();
    try: price=Decimal(request.form.get('price','0') or 0); comm=Decimal(request.form.get('commission','10') or 10); limit=int(request.form.get('product_limit','5') or 5)
    except Exception: price=Decimal('0'); comm=Decimal('10'); limit=5
    if not name or not slug: flash('Tarif nomi va slug kerak.','danger'); return redirect(url_for('business.admin_plans'))
    if SellerPlan.query.filter(or_(SellerPlan.name.ilike(name),SellerPlan.slug==slug)).first(): flash('Bu tarif allaqachon mavjud.','danger'); return redirect(url_for('business.admin_plans'))
    db.session.add(SellerPlan(name=name,slug=slug,monthly_price=max(price,Decimal('0')),commission_rate=min(max(comm,Decimal('0')),Decimal('100')),product_limit=max(limit,1),highlighted=request.form.get('highlighted')=='on',priority_moderation=request.form.get('priority')=='on',description=request.form.get('description','').strip())); db.session.commit(); flash('Tarif qo‘shildi.','success'); return redirect(url_for('business.admin_plans'))

@bp.post('/admin/tariflar/subscription/<int:id>/approve')
@login_required
@admin_required
def admin_subscription_approve(id):
    sub=SellerSubscription.query.get_or_404(id)
    if sub.status not in {'PENDING','PAYMENT_SUBMITTED'}:
        flash('Bu tarif so‘rovi allaqachon qayta ishlangan.', 'info')
        return redirect(url_for('business.admin_plans'))
    SellerSubscription.query.filter_by(seller_id=sub.seller_id,status='ACTIVE').update({'status':'EXPIRED'})
    sub.status='ACTIVE'; sub.started_at=_now(); sub.expires_at=_now()+timedelta(days=30)
    db.session.commit(); notify(sub.seller.user_id,'Tarif faollashtirildi',f'{sub.plan.name} tarifingiz faollashtirildi.')
    flash('Tarif faollashtirildi.','success'); return redirect(url_for('business.admin_plans'))

@bp.post('/admin/tariflar/subscription/<int:id>/reject')
@login_required
@admin_required
def admin_subscription_reject(id):
    sub=SellerSubscription.query.get_or_404(id); sub.status='REJECTED'; db.session.commit(); flash('Tarif so‘rovi rad etildi.','warning'); return redirect(url_for('business.admin_plans'))

@bp.post('/admin/tariflar/<int:id>/tahrirlash')
@login_required
@admin_required
def admin_plan_edit(id):
    plan = SellerPlan.query.get_or_404(id)
    name = request.form.get('name','').strip()
    slug = request.form.get('slug','').strip().lower()
    description = request.form.get('description','').strip()
    try:
        price = Decimal(request.form.get('price','0') or 0)
        commission = Decimal(request.form.get('commission','10') or 10)
        product_limit = int(request.form.get('product_limit','1') or 1)
    except Exception:
        flash('Tarif qiymatlari noto‘g‘ri kiritildi.', 'danger')
        return redirect(url_for('business.admin_plans'))
    duplicate = SellerPlan.query.filter(or_(SellerPlan.name.ilike(name), SellerPlan.slug == slug), SellerPlan.id != plan.id).first() if name and slug else None
    if not name or not slug:
        flash('Tarif nomi va slug majburiy.', 'danger')
    elif duplicate:
        flash('Bu tarif nomi yoki slug boshqa tarifda ishlatilgan.', 'danger')
    elif price < 0 or commission < 0 or commission > 100 or product_limit < 1:
        flash('Tarif qiymatlari chegaradan tashqarida.', 'danger')
    else:
        plan.name=name; plan.slug=slug; plan.monthly_price=price; plan.commission_rate=commission; plan.product_limit=product_limit
        plan.highlighted=request.form.get('highlighted')=='on'; plan.priority_moderation=request.form.get('priority')=='on'; plan.description=description or None
        db.session.commit(); flash(f'“{plan.name}” tarifi yangilandi.', 'success')
    return redirect(url_for('business.admin_plans'))

@bp.post('/admin/tariflar/<int:id>/holat')
@login_required
@admin_required
def admin_plan_toggle(id):
    plan=SellerPlan.query.get_or_404(id); plan.enabled=not plan.enabled; db.session.commit()
    flash(f'“{plan.name}” tarifi ' + ('faollashtirildi.' if plan.enabled else 'vaqtincha yopildi.'), 'success')
    return redirect(url_for('business.admin_plans'))


@bp.get('/admin/tariflar/subscription/<int:id>/chek')
@login_required
@admin_required
def admin_subscription_receipt(id):
    from pathlib import Path
    sub=SellerSubscription.query.get_or_404(id)
    path=getattr(sub,'receipt_path',None)
    if not path or not Path(path).is_file():
        return render_template('admin/file_unavailable.html', title='Tarif cheki topilmadi', message='Ushbu tarif to‘lovi uchun chek fayli mavjud emas.'),404
    return __import__('flask').send_file(path, as_attachment=False, download_name=getattr(sub,'receipt_original_name',None) or 'tarif-cheki', conditional=True)

@bp.get('/admin/support')
@login_required
@admin_required

def admin_support():
    tickets=SupportTicket.query.order_by(SupportTicket.updated_at.desc()).limit(300).all(); return render_template('business/admin_support.html',tickets=tickets)

@bp.get('/admin/shikoyatlar')
@login_required
@admin_required

def admin_reports():
    reports=ConfigReport.query.order_by(ConfigReport.created_at.desc()).limit(300).all(); fraud=FraudFlag.query.order_by(FraudFlag.created_at.desc()).limit(100).all(); return render_template('business/admin_reports.html',reports=reports,fraud=fraud)

@bp.post('/admin/shikoyatlar/<int:id>/resolve')
@login_required
@admin_required

def resolve_report(id):
    report=ConfigReport.query.get_or_404(id); report.status='RESOLVED'; db.session.commit(); flash('Shikoyat yopildi.','success'); return redirect(url_for('business.admin_reports'))

@bp.post('/admin/fraud/<int:id>/resolve')
@login_required
@admin_required

def resolve_fraud(id):
    flag=FraudFlag.query.get_or_404(id); flag.status='RESOLVED'; db.session.commit(); flash('Fraud belgisi yopildi.','success'); return redirect(url_for('business.admin_reports'))

@bp.post('/admin/support/<int:id>/status')
@login_required
@admin_required

def ticket_status(id):
    ticket=SupportTicket.query.get_or_404(id); status=request.form.get('status','OPEN'); ticket.status=status; ticket.updated_at=_now(); db.session.commit(); return redirect(url_for('business.admin_support'))

@bp.get('/admin/referral')
@login_required
@admin_required

def admin_referral():
    refs=ReferralCode.query.order_by(ReferralCode.signups.desc(),ReferralCode.clicks.desc()).limit(200).all(); return render_template('business/admin_referral.html', referrals=refs)
