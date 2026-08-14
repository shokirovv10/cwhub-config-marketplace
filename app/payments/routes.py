from flask import render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Order, PaymentReceipt, PaymentStatus, PaymentCard
from ..services.storage_service import storage
from ..services.security_service import sha256_file
from ..services.settings_service import payment_settings
from ..services.download_service import authorize, log_download
from . import bp

@bp.route('/checkout/<int:order_id>', methods=['GET', 'POST'])
@login_required
def checkout(order_id):
    order = Order.query.filter_by(id=order_id, buyer_id=current_user.id).first_or_404()
    settings = payment_settings()
    if order.status == 'COMPLETED':
        return redirect(url_for('orders.detail', id=order.id))
    if not settings.manual_enabled:
        flash('Hozircha manual payment yopiq.', 'warning')
        return redirect(url_for('orders.detail', id=order.id))
    if request.method == 'POST':
        receipt = request.files.get('receipt')
        receipt_token = request.form.get('receipt_token','').strip()
        if (not receipt or not receipt.filename) and not receipt_token:
            flash('Chekni yuklang.', 'danger')
        else:
            try:
                if receipt_token:
                    path, original, _ = storage().consume_temp(receipt_token, current_user.id, 'receipts')
                else:
                    ext = receipt.filename.rsplit('.', 1)[-1].lower() if '.' in receipt.filename else ''
                    if ext not in {'png', 'jpg', 'jpeg', 'webp', 'pdf'}:
                        flash('Faqat PNG/JPG/WEBP/PDF qabul qilinadi.', 'danger')
                        return render_template('payments/checkout.html', order=order, settings=settings, cards=PaymentCard.query.filter_by(enabled=True).order_by(PaymentCard.created_at.desc()).all())
                    path, original, _ = storage().save(receipt, 'receipts', receipt.filename)
                
                file_hash=sha256_file(path)
                duplicate = PaymentReceipt.query.filter(PaymentReceipt.sha256 == file_hash, PaymentReceipt.payment_id != order.payment.id).first()
                if duplicate:
                    from ..models import FraudFlag
                    db.session.add(FraudFlag(user_id=current_user.id,kind='DUPLICATE_RECEIPT',severity='HIGH',reference_type='PAYMENT',reference_id=str(order.payment.id),details='Bir xil chek fayli avval ishlatilgan.'))
                    db.session.rollback()
                    storage().delete(path)
                    flash('Bu chek avval ishlatilgan. To‘lov tekshiruvga yuborilmadi.', 'danger')
                    return redirect(url_for('orders.detail', id=order.id))
                old = order.payment.receipt
                if old:
                    storage().delete(old.file_path)
                    old.file_path = path; old.original_name = original; old.sha256=file_hash
                else:
                    db.session.add(PaymentReceipt(payment_id=order.payment.id, file_path=path, original_name=original, sha256=file_hash))
                db.session.commit()
                flash('Chek yuborildi. Admin tasdiqlashini kuting.', 'success')
                return redirect(url_for('orders.detail', id=order.id))
            except (PermissionError, FileNotFoundError, ValueError) as exc:
                db.session.rollback()
                flash(f'Chekni saqlashda xato: {exc}', 'danger')
    return render_template('payments/checkout.html', order=order, settings=settings, cards=PaymentCard.query.filter_by(enabled=True).order_by(PaymentCard.created_at.desc()).all())

@bp.get('/download/<int:order_id>/<int:config_id>')
@login_required
def download(order_id, config_id):
    try:
        order, item = authorize(current_user, order_id, config_id)
        # Yuklash statistikasi xato qilsa ham xaridorning qonuniy fayl yuklab olishiga to‘sqinlik qilmasin.
        try:
            log_download(current_user, order, item, request.remote_addr)
        except Exception:
            db.session.rollback()
        return send_file(item.config.file_path, as_attachment=True, download_name=item.config.file_original_name or 'cwhub-config.cfg', conditional=True)
    except PermissionError:
        abort(403)
    except FileNotFoundError:
        abort(404)
