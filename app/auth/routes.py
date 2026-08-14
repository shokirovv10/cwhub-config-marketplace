from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import datetime, timedelta
import hashlib, secrets, smtplib
from email.message import EmailMessage
import logging
from ..extensions import db, limiter
from ..models import User, Wallet, ReferralCode, ReferralAttribution, SecurityEvent, PasswordResetToken
from . import bp
from .forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm

logger = logging.getLogger(__name__)

@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('10/minute')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lstrip('@')
        email = form.email.data.strip().lower()
        username_key = username.casefold()
        try:
            # Keep the checks separate so an older/partially migrated database can be
            # diagnosed cleanly and does not leave the session in a failed transaction.
            existing_username = User.query.filter_by(username_key=username_key).first()
            existing_email = User.query.filter(User.email.ilike(email)).first()
            if existing_username or existing_email:
                flash('Foydalanuvchi nomi yoki elektron pochta band.', 'danger')
            else:
                user = User(username=username, username_key=username_key, email=email)
                user.set_password(form.password.data)
                user.wallet = Wallet()
                db.session.add(user)
                db.session.flush()
                ref_code = request.cookies.get('cwhub_ref') or request.args.get('ref') or request.form.get('referral_code')
                if ref_code:
                    ref = ReferralCode.query.filter_by(code=ref_code.strip().upper()).first()
                    if ref and ref.user_id != user.id and not ReferralAttribution.query.filter_by(referred_id=user.id).first():
                        db.session.add(ReferralAttribution(referrer_id=ref.user_id,referred_id=user.id,code=ref.code))
                        ref.signups += 1
                db.session.add(SecurityEvent(user_id=user.id,event_type='REGISTER',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500]))
                db.session.commit()
                login_user(user)
                flash('Xush kelibsiz! Hisobingiz yaratildi.', 'success')
                return redirect(url_for('main.index'))
        except IntegrityError:
            db.session.rollback()
            logger.warning("Ro'yxatdan o'tishda DB integrity xatosi: username=%s email=%s", username, email, exc_info=True)
            flash('Bu foydalanuvchi nomi yoki elektron pochta allaqachon band.', 'danger')
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Ro'yxatdan o'tishda SQLAlchemy xatosi: username=%s email=%s", username, email)
            flash("Server bazasida vaqtinchalik xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.", 'danger')
        except Exception:
            db.session.rollback()
            logger.exception("Ro'yxatdan o'tishda kutilmagan xato")
            flash("Ro'yxatdan o'tishda server xatosi yuz berdi. Iltimos, qayta urinib ko'ring.", "danger")
    return render_template('auth/register.html', form=form)

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('12/minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        ident = form.identifier.data.strip()
        key = ident.lower()
        user = User.query.filter(or_(User.email.ilike(key), User.username.ilike(ident))).first()
        if not user or not user.check_password(form.password.data):
            db.session.add(SecurityEvent(user_id=(user.id if user else None),event_type='LOGIN_FAILED',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500],details='Noto‘g‘ri login ma’lumoti')); db.session.commit()
            flash("Kirish ma’lumotlari yoki parol noto'g'ri.", 'danger')
        elif user.is_banned:
            flash('Hisobingiz vaqtincha bloklangan.', 'danger')
        else:
            login_user(user, remember=form.remember.data)
            db.session.add(SecurityEvent(user_id=user.id,event_type='LOGIN_SUCCESS',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500])); db.session.commit()
            next_url = request.args.get('next')
            return redirect(next_url if next_url and next_url.startswith('/') else url_for('main.index'))
    return render_template('auth/login.html', form=form)


@bp.route('/forgot-password', methods=['GET','POST'])
@limiter.limit('5/hour')
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        key = identifier.casefold()
        user = User.query.filter(or_(User.email.ilike(identifier.lower()), User.username_key == key)).first()
        code_hash = hashlib.sha256(form.recovery_code.data.strip().encode()).hexdigest()
        record = None
        if user:
            record = PasswordResetToken.query.filter_by(user_id=user.id, token_hash=code_hash, used_at=None).order_by(PasswordResetToken.expires_at.desc()).first()
        if not record or record.expires_at < datetime.utcnow():
            flash('Foydalanuvchi nomi yoki tiklash kodi noto‘g‘ri, yoki kodning amal qilish muddati tugagan.', 'danger')
            return render_template('auth/forgot_password.html', form=form)
        token = form.recovery_code.data.strip()
        return redirect(url_for('auth.reset_password', token=token))
    return render_template('auth/forgot_password.html', form=form)

@bp.route('/reset-password/<token>', methods=['GET','POST'])
@limiter.limit('10/hour')
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    record = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    if not record or record.used_at or record.expires_at < datetime.utcnow():
        flash('Parolni tiklash havolasi yaroqsiz yoki muddati tugagan.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        record.user.set_password(form.password.data); record.used_at=datetime.utcnow()
        db.session.add(SecurityEvent(user_id=record.user_id,event_type='PASSWORD_RESET',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500]))
        db.session.commit(); flash('Parolingiz muvaffaqiyatli yangilandi. Endi yangi parol bilan kiring.', 'success'); return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)

@bp.post('/logout')
def logout():
    if current_user.is_authenticated:
        db.session.add(SecurityEvent(user_id=current_user.id,event_type='LOGOUT',ip=request.remote_addr,user_agent=request.headers.get('User-Agent','')[:500]))
        db.session.commit()
    logout_user()
    flash('Siz tizimdan chiqdingiz.', 'info')
    return redirect(url_for('main.index'))
