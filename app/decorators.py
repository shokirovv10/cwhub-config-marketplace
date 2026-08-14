from functools import wraps
from flask import abort, request
from flask_login import current_user
from .extensions import db
from .models import SellerProfile, Wallet

# Each helper-admin scope only sees and can call the routes belonging to it.
# SUPER_ADMIN bypasses the matrix. FULL helper admins use the ADMIN scope.
SCOPE_ENDPOINTS = {
    'ADMIN': {
        'admin.dashboard','admin.configs','admin.payments','admin.orders','admin.withdrawals','admin.sellers',
        'admin.catalog','admin.finance','admin.announcements','admin.activity','business.admin_plans',
        'business.admin_support','business.admin_reports','business.admin_referral','admin.seller_title',
    },
    'MODERATOR': {
        'admin.configs','admin.sellers','admin.catalog','business.admin_reports','admin.seller_title',
    },
    'SUPPORT': {
        'business.admin_support',
    },
    'FINANCE': {
        'admin.payments','admin.withdrawals','admin.finance','business.admin_plans',
    },
}

def scope_allows(endpoint):
    if not current_user.is_authenticated or getattr(current_user, 'is_banned', False):
        return False
    if current_user.is_super_admin:
        return True
    scope = getattr(current_user, 'admin_scope', None)
    return endpoint in SCOPE_ENDPOINTS.get(scope, set())

def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles or getattr(current_user, 'is_banned', False):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'is_banned', False) or not current_user.is_admin:
            abort(403)
        # Route-level scope enforcement. Super Admin has all rights.
        if not current_user.is_super_admin and not scope_allows(request.endpoint):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def finance_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'is_banned', False):
            abort(403)
        if current_user.is_super_admin:
            return fn(*args, **kwargs)
        if current_user.role != 'ADMIN' or getattr(current_user, 'admin_scope', None) != 'FINANCE':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def restricted_admin_read_or_super(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'is_banned', False):
            abort(403)
        if current_user.is_super_admin:
            return fn(*args, **kwargs)
        if current_user.role != 'ADMIN':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def super_admin_required(fn):
    return roles_required('SUPER_ADMIN')(fn)

def seller_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user, 'is_banned', False):
            abort(403)
        if current_user.role == 'ADMIN':
            abort(403)
        profile = current_user.seller_profile
        if current_user.is_super_admin and not profile:
            profile = SellerProfile(
                user_id=current_user.id,
                nickname=current_user.username,
                description='CwHUB Super Admin sotuv profili',
                approved=True,
                verification_status='APPROVED',
            )
            current_user.is_verified = True
            if not current_user.wallet:
                current_user.wallet = Wallet()
            db.session.add(profile)
            db.session.commit()
        if not profile or not profile.approved:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper
