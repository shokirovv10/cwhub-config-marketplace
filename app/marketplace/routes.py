from decimal import Decimal
from pathlib import Path
from flask import render_template, request, abort, flash, redirect, url_for, send_file, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_, asc, desc
from ..extensions import db
from ..models import Config, Category, ConfigType, Game, Order, OrderItem, Review, Wishlist, CartItem
from ..services.storage_service import storage
from ..services.order_service import create_order
from . import bp
from .forms import ReviewForm

@bp.get('/configs')
def configs():
    query = Config.query.filter_by(status='APPROVED')
    search = request.args.get('q', '').strip()
    game_id = request.args.get('game', type=int)
    category_id = request.args.get('category', type=int)
    type_id = request.args.get('type', type=int)
    sort = request.args.get('sort', 'newest')
    min_price = request.args.get('min', type=float)
    max_price = request.args.get('max', type=float)

    if search:
        query = query.filter(or_(
            Config.name.ilike(f'%{search}%'),
            Config.description.ilike(f'%{search}%'),
            Config.tags.ilike(f'%{search}%'),
        ))
    if game_id:
        query = query.filter_by(game_id=game_id)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if type_id:
        query = query.filter_by(type_id=type_id)
    if min_price is not None:
        query = query.filter(Config.price >= Decimal(str(min_price)))
    if max_price is not None:
        query = query.filter(Config.price <= Decimal(str(max_price)))

    if sort == 'popular':
        query = query.order_by(desc(Config.download_count), desc(Config.created_at))
    elif sort == 'rating':
        query = query.order_by(desc(Config.download_count), desc(Config.created_at))
    elif sort == 'price_low':
        query = query.order_by(asc(Config.price), desc(Config.created_at))
    elif sort == 'price_high':
        query = query.order_by(desc(Config.price), desc(Config.created_at))
    else:
        query = query.order_by(desc(Config.created_at))

    page = query.paginate(page=request.args.get('page', 1, type=int), per_page=12, error_out=False)
    return render_template('marketplace/list.html', page=page, categories=Category.query.order_by(Category.name).all(), types=ConfigType.query.order_by(ConfigType.name).all(), games=Game.query.order_by(Game.name).all())

@bp.get('/config/<slug>')
def config_detail(slug):
    config = Config.query.filter_by(slug=slug, status='APPROVED').first_or_404()
    config.view_count += 1
    db.session.commit()
    ratings = [review.rating for review in config.reviews]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else 0
    purchased = False
    purchased_order_id = None
    if current_user.is_authenticated:
        purchased_order = Order.query.join(OrderItem).filter(
            Order.buyer_id == current_user.id,
            Order.status == 'COMPLETED',
            OrderItem.config_id == config.id,
        ).order_by(Order.created_at.desc()).first()
        purchased = purchased_order is not None
        purchased_order_id = purchased_order.id if purchased_order else None
    wishlisted = False
    if current_user.is_authenticated:
        wishlisted = Wishlist.query.filter_by(user_id=current_user.id, config_id=config.id).first() is not None
    return render_template('marketplace/detail.html', config=config, avg=avg, purchased=purchased, purchased_order_id=purchased_order_id, wishlisted=wishlisted, review_form=ReviewForm())

@bp.get('/media/config/<int:id>')
def media_image(id):
    config = Config.query.filter_by(id=id, status='APPROVED').first_or_404()
    if not config.main_image or not storage().exists(config.main_image):
        return send_file(Path(current_app.static_folder) / 'images' / 'placeholder.svg', conditional=True)
    return send_file(config.main_image, conditional=True)

@bp.post('/config/<slug>/review')
@login_required
def review(slug):
    config = Config.query.filter_by(slug=slug, status='APPROVED').first_or_404()
    purchased = Order.query.join(OrderItem).filter(
        Order.buyer_id == current_user.id,
        Order.status == 'COMPLETED',
        OrderItem.config_id == config.id,
    ).first()
    if not purchased:
        abort(403)
    form = ReviewForm()
    if form.validate_on_submit():
        review_obj = Review.query.filter_by(config_id=config.id, user_id=current_user.id).first()
        if review_obj:
            review_obj.rating = form.rating.data
            review_obj.comment = form.comment.data
        else:
            db.session.add(Review(config_id=config.id, user_id=current_user.id, rating=form.rating.data, comment=form.comment.data))
        db.session.commit()
        flash('Review saqlandi.', 'success')
    return redirect(url_for('marketplace.config_detail', slug=slug))

@bp.post('/config/<int:id>/buy')
@login_required
def buy(id):
    config = db.session.get(Config, id)
    if not config or config.status != 'APPROVED':
        abort(404)
    if config.seller.user_id == current_user.id:
        flash("O'z configingizni sotib olmaysiz.", 'warning')
        return redirect(url_for('marketplace.config_detail', slug=config.slug))
    try:
        order = create_order(current_user, [id])
        return redirect(url_for('payments.checkout', order_id=order.id))
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('marketplace.config_detail', slug=config.slug))

@bp.post('/cart/add/<int:id>')
@login_required
def cart_add(id):
    config = db.session.get(Config, id)
    if not config or config.status != 'APPROVED':
        abort(404)
    if config.seller and config.seller.user_id == current_user.id:
        flash("O‘z configingizni savatchaga qo‘sha olmaysiz.", 'warning')
        return redirect(request.referrer or url_for('marketplace.configs'))
    exists = CartItem.query.filter_by(user_id=current_user.id, config_id=id).first()
    if not exists:
        try:
            db.session.add(CartItem(user_id=current_user.id, config_id=id))
            db.session.commit()
            flash('Config savatchaga qo‘shildi.', 'success')
        except Exception:
            db.session.rollback()
            flash('Config savatchaga qo‘shilmadi. Qayta urinib ko‘ring.', 'danger')
    else:
        flash('Config allaqachon savatchada.', 'info')
    return redirect(request.referrer or url_for('marketplace.configs'))

@bp.post('/cart/remove/<int:id>')
@login_required
def cart_remove(id):
    item = CartItem.query.filter_by(user_id=current_user.id, config_id=id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect(request.referrer or url_for('marketplace.cart'))

@bp.get('/cart')
@login_required
def cart():
    # One-time migration for guests who had a session cart in older versions.
    legacy_ids = []
    for raw in session.get('cart', []):
        try: legacy_ids.append(int(raw))
        except (TypeError, ValueError): pass
    if legacy_ids:
        for cid in legacy_ids:
            cfg = db.session.get(Config, cid)
            if cfg and cfg.status == 'APPROVED' and cfg.seller and cfg.seller.user_id != current_user.id:
                if not CartItem.query.filter_by(user_id=current_user.id, config_id=cid).first():
                    db.session.add(CartItem(user_id=current_user.id, config_id=cid))
        db.session.commit()
        session.pop('cart', None)

    cart_rows = CartItem.query.filter_by(user_id=current_user.id).order_by(CartItem.created_at.desc()).all()
    cart_items = [row.config for row in cart_rows if row.config and row.config.status == 'APPROVED' and row.config.seller]
    valid_ids = {c.id for c in cart_items}
    for row in cart_rows:
        if not row.config or row.config.status != 'APPROVED' or not row.config.seller:
            db.session.delete(row)
    db.session.commit()
    total = sum((Decimal(c.price) for c in cart_items), Decimal('0'))
    coupon_code=session.get('coupon_code')
    try: coupon_discount=Decimal(str(session.get('coupon_discount','0') or '0'))
    except Exception: coupon_discount=Decimal('0')
    coupon_discount=min(max(coupon_discount,Decimal('0')),total)
    final_total=total-coupon_discount
    return render_template('cart.html', cart_items=cart_items, total=total, coupon_code=coupon_code, coupon_discount=coupon_discount, final_total=final_total)

@bp.post('/cart/clear')
@login_required
def cart_clear():
    CartItem.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
    session.pop('cart', None)
    db.session.commit()
    flash('Savatcha tozalandi.', 'info')
    return redirect(url_for('marketplace.cart'))

@bp.post('/cart/checkout')
@login_required
def cart_checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    ids = [row.config_id for row in cart_items if row.config and row.config.status == 'APPROVED']
    try:
        order = create_order(current_user, ids)
        if order:
            CartItem.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
            session.pop('coupon_code', None)
            session.pop('coupon_discount', None)
            db.session.commit()
        return redirect(url_for('payments.checkout', order_id=order.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('marketplace.cart'))


@bp.post('/config/<int:id>/wishlist')
@login_required
def wishlist_toggle(id):
    config=Config.query.filter_by(id=id,status='APPROVED').first_or_404()
    item=Wishlist.query.filter_by(user_id=current_user.id,config_id=config.id).first()
    if item:
        db.session.delete(item); flash('Config sevimlilardan olib tashlandi.','info')
    else:
        db.session.add(Wishlist(user_id=current_user.id,config_id=config.id)); flash('Config sevimlilarga qo‘shildi.','success')
    db.session.commit()
    return redirect(request.referrer or url_for('marketplace.config_detail',slug=config.slug))

@bp.get('/wishlist')
@login_required
def wishlist():
    items=Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.created_at.desc()).all()
    return render_template('wishlist.html',items=items)
