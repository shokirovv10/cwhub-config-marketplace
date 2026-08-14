import os
import re
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash, abort, send_file
from pathlib import Path
from flask_login import login_required, current_user
from sqlalchemy import func, desc
from ..extensions import db
from ..models import SellerProfile, SellerPayoutAccount, Config, Category, ConfigType, Game, OrderItem, Order, Withdrawal, SiteSettings, WalletTransaction, SellerSubscription, SellerPlan, ConfigVersion
from ..decorators import seller_required
from ..services.storage_service import storage
from ..services.security_service import scan_config_file
from ..services.wallet_service import ensure_wallet, reserve_withdrawal
from ..marketplace.forms import SellerForm, ConfigForm
from . import bp


def slugify(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:150]


def sidebar_items():
    sp = current_user.seller_profile
    return [
        {'endpoint': 'seller.dashboard', 'label': 'Boshqaruv paneli', 'icon': '⌂', 'badge': '', 'kwargs': {}},
        {'endpoint': 'seller.configs', 'label': 'Configlarim', 'icon': '▣', 'badge': len(sp.configs), 'kwargs': {}},
        {'endpoint': 'seller.add_config', 'label': 'Config yuklash', 'icon': '+', 'badge': '', 'kwargs': {}},
        {'endpoint': 'seller.transactions', 'label': 'Balans va tarix', 'icon': '₤', 'badge': '', 'kwargs': {}},
        {'endpoint': 'seller.withdraw', 'label': 'Pul yechish', 'icon': '↗', 'badge': '', 'kwargs': {}},
        {'endpoint': 'seller.payout_accounts', 'label': 'To‘lov rekvizitlari', 'icon': '▱', 'badge': '', 'kwargs': {}},
        {'endpoint': 'business.seller_plans', 'label': 'Tariflarim', 'icon': '▤', 'badge': '', 'kwargs': {}},
        {'endpoint': 'business.seller_coupons', 'label': 'Kuponlar', 'icon': '%', 'badge': '', 'kwargs': {}},
        {'endpoint': 'business.tickets', 'label': 'Yordam', 'icon': '?', 'badge': '', 'kwargs': {}},
        {'endpoint': 'business.referral_panel', 'label': 'Taklif dasturi', 'icon': '↗', 'badge': '', 'kwargs': {}},
        {'endpoint': 'main.seller_public', 'label': 'Ochiq profil', 'icon': '@', 'badge': '', 'kwargs': {'nickname': sp.nickname}},
    ]


def render_dash(template, **context):
    return render_template(
        template,
        sidebar_items=sidebar_items(),
        sidebar_kicker='Sotuvchi ish maydoni',
        sidebar_title='CwHUB Sotuvchi',
        sidebar_cta={'endpoint': 'seller.add_config', 'kwargs': {}, 'label': 'Yangi config yuklash'},
        **context,
    )

@bp.route('/apply', methods=['GET', 'POST'])
@bp.route('/apply/', methods=['GET', 'POST'])
@login_required
def apply():
    existing = current_user.seller_profile
    if existing and existing.approved:
        return redirect(url_for('seller.dashboard'))
    if existing and existing.verification_status == 'PENDING':
        return redirect(url_for('seller.verification_status'))
    form = SellerForm(obj=existing)
    if form.validate_on_submit():
        nickname = form.nickname.data.strip().lstrip('@')
        duplicate = SellerProfile.query.filter(SellerProfile.nickname.ilike(nickname), SellerProfile.id != (existing.id if existing else 0)).first()
        if duplicate:
            form.nickname.errors.append('Bu seller nickname allaqachon band.')
        else:
            document = form.verification_document.data
            temp_token = request.form.get('verification_token','').strip()
            if (not document or not document.filename) and not temp_token:
                form.verification_document.errors.append('Tasdiqlash hujjatini yuklang.')
            else:
                try:
                    if temp_token:
                        path, original, _ = storage().consume_temp(temp_token, current_user.id, 'seller_verification')
                    else:
                        ext = document.filename.rsplit('.',1)[-1].lower() if '.' in document.filename else ''
                        if ext not in {'png','jpg','jpeg','webp','pdf'}:
                            raise ValueError('Faqat PNG/JPG/WEBP/PDF qabul qilinadi.')
                        path, original, _ = storage().save(document, 'seller_verification', document.filename)
                    old_document = existing.verification_document if existing else None
                    sp = existing or SellerProfile(user_id=current_user.id, nickname=nickname)
                    sp.nickname = nickname
                    sp.description = form.description.data
                    sp.payout_info = form.payout_info.data
                    sp.approved = False
                    sp.verification_status = 'PENDING'
                    sp.verification_submitted_at = datetime.utcnow()
                    sp.verification_document_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None
                    sp.verification_document = path
                    sp.verification_original_name = original
                    sp.verification_reject_reason = None
                    db.session.add(sp)
                    db.session.commit()
                    if old_document and old_document != path:
                        storage().delete(old_document)
                    flash('Verification hujjati yuborildi. Admin tasdiqlashini kuting.', 'success')
                    return redirect(url_for('seller.verification_status'))
                except Exception as exc:
                    form.verification_document.errors.append(f'Hujjat saqlanmadi: {exc}')
    return render_template('seller/apply.html', form=form)

@bp.get('/config-image/<int:id>')
@bp.get('/config-image/<int:id>/')
@login_required
@seller_required
def config_image(id):
    if current_user.is_super_admin:
        config = db.session.get(Config, id) or abort(404)
    else:
        config = Config.query.filter_by(id=id, seller_id=current_user.seller_profile.id).first_or_404()
    if not config.main_image or not storage().exists(config.main_image):
        abort(404)
    return send_file(config.main_image, conditional=True)

@bp.get('/verification')
@bp.get('/verification/')
@login_required
def verification_status():
    sp = current_user.seller_profile
    if not sp:
        return redirect(url_for('seller.apply'))
    return render_template('seller/pending.html', seller=sp)

@bp.get('/')
@bp.get('/dashboard')
@login_required
@seller_required
def dashboard():
    sp = current_user.seller_profile
    wallet = ensure_wallet(current_user)
    items = OrderItem.query.join(Order).filter(OrderItem.seller_id == sp.id, Order.status == 'COMPLETED').all()
    sales = sum((Decimal(i.seller_amount) for i in items), Decimal('0'))
    products = len(sp.configs)
    downloads = sum(c.download_count for c in sp.configs)
    views = sum(c.view_count for c in sp.configs)
    top = sorted([c for c in sp.configs if c.status != 'DELETED'], key=lambda item: item.download_count, reverse=True)[:6]
    rating_values=[r.rating for c in sp.configs for r in c.reviews]
    avg_rating=round(sum(rating_values)/len(rating_values),1) if rating_values else 0
    completed_sales=sum(1 for x in items if x.order.status=='COMPLETED')
    seller_level=current_user.seller_title or 'Yangi sotuvchi'
    if not current_user.seller_title:
        if completed_sales >= 100 and avg_rating >= 4.7: seller_level='Top sotuvchi'
        elif completed_sales >= 30 and avg_rating >= 4.5: seller_level='Pro sotuvchi'
        elif completed_sales >= 10: seller_level='O‘sayotgan sotuvchi'
    active_sub=SellerSubscription.query.filter_by(seller_id=sp.id,status='ACTIVE').first()
    start = datetime.utcnow().date() - timedelta(days=13)
    daily = {start + timedelta(days=i): Decimal('0') for i in range(14)}
    for item in items:
        day = item.order.created_at.date()
        if day in daily:
            daily[day] += Decimal(item.seller_amount)
    chart = [{'label': day.strftime('%d'), 'amount': float(daily[day])} for day in daily]
    return render_dash('seller/dashboard.html', seller=sp, wallet=wallet, sales=sales, products=products, downloads=downloads, views=views, top=top, chart=chart, avg_rating=avg_rating, seller_level=seller_level, active_subscription=active_sub)

@bp.get('/configs')
@bp.get('/configs/')
@login_required
@seller_required
def configs():
    config_items = Config.query.filter_by(seller_id=current_user.seller_profile.id).order_by(Config.created_at.desc()).all()
    return render_dash('seller/configs.html', config_items=config_items)

@bp.route('/configs/add', methods=['GET', 'POST'])
@bp.route('/configs/add/', methods=['GET', 'POST'])
@login_required
@seller_required
def add_config():
    form = ConfigForm()
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.type_id.choices = [(t.id, t.name) for t in ConfigType.query.order_by(ConfigType.name).all()]
    form.game_id.choices = [(g.id, g.name) for g in Game.query.order_by(Game.name).all()]
    if form.validate_on_submit():
        return _save_config(form, None)
    return render_dash('seller/config_form.html', form=form, editing=False, config=None)

@bp.route('/configs/<int:id>/edit', methods=['GET', 'POST'])
@bp.route('/configs/<int:id>/edit/', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_config(id):
    if current_user.is_super_admin:
        config = db.session.get(Config, id) or abort(404)
    else:
        config = Config.query.filter_by(id=id, seller_id=current_user.seller_profile.id).first_or_404()
    form = ConfigForm(obj=config)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.type_id.choices = [(t.id, t.name) for t in ConfigType.query.order_by(ConfigType.name).all()]
    form.game_id.choices = [(g.id, g.name) for g in Game.query.order_by(Game.name).all()]
    if request.method == 'GET':
        form.category_id.data = config.category_id
        form.type_id.data = config.type_id
        form.game_id.data = config.game_id
    if form.validate_on_submit():
        return _save_config(form, config)
    return render_dash('seller/config_form.html', form=form, editing=True, config=config)


def _save_config(form, config):
    ss = SiteSettings.get_or_create()
    active_sub = SellerSubscription.query.filter_by(seller_id=current_user.seller_profile.id, status='ACTIVE').order_by(SellerSubscription.created_at.desc()).first()
    plan_limit = active_sub.plan.product_limit if active_sub else 5
    if config is None and Config.query.filter_by(seller_id=current_user.seller_profile.id).filter(Config.status != 'DELETED').count() >= plan_limit:
        flash(f'Sizning tarifingiz limiti {plan_limit} ta config.', 'warning')
        return render_dash('seller/config_form.html', form=form, editing=False, config=None)
    file = form.config_file.data
    file_token = request.form.get('config_file_token','').strip()
    if config is None and (not file or not file.filename) and not file_token:
        form.config_file.errors.append('Config faylini tanlang.')
        return render_dash('seller/config_form.html', form=form, editing=False, config=None)

    if file_token:
        try:
            temp_path, temp_original, temp_size = storage().consume_temp(file_token, current_user.id, 'config_files')
            clean, reason = scan_config_file(temp_path, temp_original)
            if not clean:
                storage().delete(temp_path)
                form.config_file.errors.append(reason)
                return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)
            ext = temp_original.rsplit('.',1)[-1].lower() if '.' in temp_original else ''
            if ext not in {'cfg','zip','rar','txt'}:
                storage().delete(temp_path)
                form.config_file.errors.append('Bu config fayl turiga ruxsat berilmagan.')
                return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)
            old_file = config.file_path if config else None
            if config and old_file:
                db.session.add(ConfigVersion(config_id=config.id, version_label=config.version or 'oldingi-versiya', file_path=old_file, file_original_name=config.file_original_name, file_size=config.file_size, changelog=request.form.get('changelog','').strip() or 'Yangi fayl yuklandi.', created_by=current_user.id))
            if config is None:
                config = Config(seller_id=current_user.seller_profile.id)
                db.session.add(config)
            config.file_path = temp_path
            config.file_original_name = temp_original
            config.file_size = temp_size
            config.file_mime = file.mimetype if file else 'application/octet-stream'
            # Eski fayl versiya sifatida saqlanadi; o‘chirilmaydi.
            file = None
        except Exception as exc:
            form.config_file.errors.append(f'Config fayli saqlanmadi: {exc}')
            return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)

    if file and file.filename:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        allowed = {x.strip().lower().lstrip('.') for x in (ss.allowed_extensions or '').split(',') if x.strip()}
        if ext not in allowed:
            form.config_file.errors.append('Bu fayl kengaytmasiga ruxsat berilmagan.')
            return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)
        if ext not in {'cfg', 'zip', 'rar', 'txt'}:
            form.config_file.errors.append('Nomaqbul config file turi.')
            return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)
        blocked_mimes = {'text/html', 'application/javascript', 'text/javascript', 'application/x-msdownload'}
        if (file.mimetype or '').lower() in blocked_mimes:
            form.config_file.errors.append('Bu fayl turi xavfsiz emas.')
            return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)

    old_file = config.file_path if config else None
    old_image = config.main_image if config else None
    if config is None:
        config = Config(seller_id=current_user.seller_profile.id)
        db.session.add(config)

    config.category_id = form.category_id.data
    config.type_id = form.type_id.data
    config.game_id = form.game_id.data
    config.name = form.name.data.strip()
    config.slug = config.slug if config.id else f"{slugify(form.name.data)}-{os.urandom(3).hex()}"
    config.short_description = form.short_description.data
    config.description = form.description.data
    config.version = form.version.data
    config.price = form.price.data
    config.tags = form.tags.data
    config.demo_url = form.demo_url.data

    if file and file.filename:
        path, original, size = storage().save(file, 'config_files', file.filename)
        clean, reason = scan_config_file(path, original)
        if not clean:
            storage().delete(path)
            form.config_file.errors.append(reason)
            return render_dash('seller/config_form.html', form=form, editing=config is not None, config=config)
        if config and old_file and config.file_path != path:
            db.session.add(ConfigVersion(config_id=config.id, version_label=config.version or 'oldingi-versiya', file_path=old_file, file_original_name=config.file_original_name, file_size=config.file_size, changelog=request.form.get('changelog','').strip() or 'Yangi fayl yuklandi.', created_by=current_user.id))
        config.file_path = path
        config.file_original_name = original
        config.file_size = size
        config.file_mime = file.mimetype
        # Eski fayl ConfigVersion orqali saqlanadi; o‘chirilmaydi.
    elif not config.file_path:
        flash('Config fayli kerak.', 'danger')
        return render_dash('seller/config_form.html', form=form, editing=config.id is not None, config=config)

    image = form.cover_image.data
    image_token = request.form.get('cover_image_token','').strip()
    if image_token:
        try:
            path, _, _ = storage().consume_temp(image_token, current_user.id, 'config_images')
            config.main_image = path
            if old_image and old_image != path:
                storage().delete(old_image)
        except Exception as exc:
            form.cover_image.errors.append(f'Muqova rasmi saqlanmadi: {exc}')
            return render_dash('seller/config_form.html', form=form, editing=config.id is not None, config=config)
    elif image and image.filename:
        allowed_image_mimes = {'image/png', 'image/jpeg', 'image/webp'}
        if (image.mimetype or '').lower() not in allowed_image_mimes:
            form.cover_image.errors.append('Cover image MIME turi noto‘g‘ri.')
            return render_dash('seller/config_form.html', form=form, editing=config.id is not None, config=config)
        path, _, _ = storage().save(image, 'config_images', image.filename)
        config.main_image = path
        if old_image and old_image != path:
            storage().delete(old_image)

    config.status = 'APPROVED' if ss.auto_approve_products else 'PENDING'
    config.reject_reason = None
    db.session.commit()
    flash('Config yangilandi va moderation navbatiga yuborildi.' if config.status == 'PENDING' else 'Config publish qilindi.', 'success')
    return redirect(url_for('seller.configs'))


@bp.get('/configs/<int:id>/versions')
@bp.get('/configs/<int:id>/versions/')
@login_required
@seller_required
def config_versions(id):
    config = db.session.get(Config, id) or abort(404)
    if not current_user.is_super_admin and config.seller_id != current_user.seller_profile.id: abort(403)
    versions = ConfigVersion.query.filter_by(config_id=id).order_by(ConfigVersion.created_at.desc()).all()
    return render_dash('seller/config_versions.html', config=config, versions=versions)


@bp.get('/configs/<int:id>/versions/<int:version_id>/download')
@bp.get('/configs/<int:id>/versions/<int:version_id>/download/')
@login_required
@seller_required
def config_version_download(id, version_id):
    config = db.session.get(Config, id) or abort(404)
    if not current_user.is_super_admin and config.seller_id != current_user.seller_profile.id: abort(403)
    version = ConfigVersion.query.filter_by(id=version_id, config_id=id).first_or_404()
    if not storage().exists(version.file_path): abort(404)
    return send_file(version.file_path, as_attachment=True, download_name=version.file_original_name, conditional=True)

@bp.post('/configs/<int:id>/delete')
@bp.post('/configs/<int:id>/delete/')
@login_required
@seller_required
def delete_config(id):
    config = Config.query.filter_by(id=id, seller_id=current_user.seller_profile.id).first_or_404()
    config.status = 'DELETED'
    db.session.commit()
    flash('Config yashirildi.', 'success')
    return redirect(url_for('seller.configs'))

@bp.route('/payout-accounts', methods=['GET', 'POST'])
@bp.route('/payout-accounts/', methods=['GET', 'POST'])
@login_required
@seller_required
def payout_accounts():
    seller_id = current_user.seller_profile.id
    if request.method == 'POST':
        method = request.form.get('method','Karta').strip() or 'Karta'
        label = request.form.get('label','Asosiy hisob').strip() or 'Asosiy hisob'
        destination = request.form.get('destination','').strip()
        make_default = request.form.get('is_default') == 'on'
        if not destination:
            flash('Karta yoki hisob raqamini kiriting.', 'danger')
        else:
            if make_default:
                SellerPayoutAccount.query.filter_by(seller_id=seller_id, is_default=True).update({'is_default':False}, synchronize_session=False)
            exists = SellerPayoutAccount.query.filter_by(seller_id=seller_id, destination=destination).first()
            if exists:
                flash('Bu rekvizit allaqachon qo‘shilgan.', 'info')
            else:
                db.session.add(SellerPayoutAccount(seller_id=seller_id, method=method, label=label, destination=destination, is_default=make_default or SellerPayoutAccount.query.filter_by(seller_id=seller_id).count()==0))
                db.session.commit()
                flash('To‘lov rekviziti qo‘shildi.', 'success')
                return redirect(url_for('seller.payout_accounts'))
    accounts = SellerPayoutAccount.query.filter_by(seller_id=seller_id).order_by(SellerPayoutAccount.is_default.desc(), SellerPayoutAccount.created_at.desc()).all()
    return render_dash('seller/payout_accounts.html', accounts=accounts)

@bp.post('/payout-accounts/<int:id>/default')
@login_required
@seller_required
def payout_default(id):
    account = SellerPayoutAccount.query.filter_by(id=id, seller_id=current_user.seller_profile.id).first_or_404()
    SellerPayoutAccount.query.filter_by(seller_id=current_user.seller_profile.id, is_default=True).update({'is_default':False}, synchronize_session=False)
    account.is_default=True
    db.session.commit()
    flash('Asosiy to‘lov rekviziti tanlandi.', 'success')
    return redirect(url_for('seller.payout_accounts'))

@bp.post('/payout-accounts/<int:id>/delete')
@login_required
@seller_required
def payout_delete(id):
    account = SellerPayoutAccount.query.filter_by(id=id, seller_id=current_user.seller_profile.id).first_or_404()
    db.session.delete(account)
    db.session.commit()
    # Remaining accountlardan birini default qilish
    remaining=SellerPayoutAccount.query.filter_by(seller_id=current_user.seller_profile.id).order_by(SellerPayoutAccount.created_at.asc()).first()
    if remaining and not remaining.is_default:
        remaining.is_default=True
        db.session.commit()
    flash('To‘lov rekviziti o‘chirildi.', 'success')
    return redirect(url_for('seller.payout_accounts'))

@bp.route('/withdraw', methods=['GET', 'POST'])
@bp.route('/withdraw/', methods=['GET', 'POST'])
@login_required
@seller_required
def withdraw():
    wallet = ensure_wallet(current_user)
    settings = SiteSettings.get_or_create()
    if request.method == 'POST':
        try:
            amount = Decimal(request.form.get('amount', '0'))
        except Exception:
            amount = Decimal('0')
        method = request.form.get('method', 'Card').strip() or 'Card'
        destination = request.form.get('destination', '').strip()
        comment = request.form.get('comment', '').strip()
        if amount <= 0:
            flash('Amount 0 dan katta bo‘lishi kerak.', 'danger')
        elif amount < Decimal(settings.minimum_withdrawal):
            flash(f'Minimum withdrawal {settings.minimum_withdrawal} UZS.', 'danger')
        elif not destination:
            flash('Payout destination kiriting.', 'danger')
        else:
            withdrawal = Withdrawal(seller_id=current_user.seller_profile.id, amount=amount, method=method, payout_destination=destination, comment=comment)
            db.session.add(withdrawal)
            db.session.flush()
            try:
                reserve_withdrawal(current_user, amount, withdrawal.id)
                db.session.commit()
                flash("Withdrawal so'rovi yuborildi.", 'success')
                return redirect(url_for('seller.withdraw'))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')
    history = Withdrawal.query.filter_by(seller_id=current_user.seller_profile.id).order_by(Withdrawal.created_at.desc()).all()
    payout_accounts = SellerPayoutAccount.query.filter_by(seller_id=current_user.seller_profile.id).order_by(SellerPayoutAccount.is_default.desc(), SellerPayoutAccount.created_at.desc()).all()
    return render_dash('seller/withdraw.html', wallet=wallet, settings=settings, history=history, payout_accounts=payout_accounts)

@bp.get('/transactions')
@bp.get('/transactions/')
@login_required
@seller_required
def transactions():
    wallet = ensure_wallet(current_user)
    tx = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(WalletTransaction.created_at.desc()).limit(150).all()
    return render_dash('seller/transactions.html', wallet=wallet, transactions=tx)
