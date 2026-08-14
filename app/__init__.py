import os
import logging
from flask import Flask, render_template, request, jsonify, current_app, send_from_directory, abort
from jinja2 import ChainableUndefined
from flask_login import current_user
from decimal import Decimal
from config import BaseConfig
from .extensions import db, login_manager, csrf, limiter, migrate

def _ensure_legacy_schema():
    """Bring older CwHUB PostgreSQL/SQLite databases up to the current User schema.

    This is intentionally limited to backward-compatible user/account columns that
    are required by authentication and registration. It is safe to run on every boot.
    """
    from sqlalchemy import inspect, text
    engine = db.engine
    inspector = inspect(engine)
    if 'user' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('user')}
    is_pg = engine.dialect.name == 'postgresql'

    def add_column(name, sql_type, nullable=True, default=None):
        nonlocal columns
        if name in columns:
            return
        quoted = f'"{name}"'
        if is_pg:
            statement = f'ALTER TABLE "user" ADD COLUMN {quoted} {sql_type}'
        else:
            statement = f'ALTER TABLE "user" ADD COLUMN {quoted} {sql_type}'
        db.session.execute(text(statement))
        columns.add(name)

    # Nullable first for fields that may not exist in older rows.
    add_column('description', 'TEXT', nullable=True)
    add_column('avatar', 'VARCHAR(255)', nullable=True)

    # These account flags must have a value for existing rows.
    if 'is_active_user' not in columns:
        add_column('is_active_user', 'BOOLEAN')
        db.session.execute(text('UPDATE "user" SET "is_active_user" = TRUE WHERE "is_active_user" IS NULL'))
        try:
            if is_pg:
                db.session.execute(text('ALTER TABLE "user" ALTER COLUMN "is_active_user" SET DEFAULT TRUE'))
                db.session.execute(text('ALTER TABLE "user" ALTER COLUMN "is_active_user" SET NOT NULL'))
            else:
                # SQLite cannot reliably add NOT NULL after the fact; values are populated.
                pass
        except Exception:
            db.session.rollback()
            raise

    if 'is_verified' not in columns:
        add_column('is_verified', 'BOOLEAN')
        db.session.execute(text('UPDATE "user" SET "is_verified" = FALSE WHERE "is_verified" IS NULL'))
        if is_pg:
            db.session.execute(text('ALTER TABLE "user" ALTER COLUMN "is_verified" SET DEFAULT FALSE'))
            db.session.execute(text('ALTER TABLE "user" ALTER COLUMN "is_verified" SET NOT NULL'))

    # username_key is required by registration/login. Backfill it before making it unique.
    if 'username_key' not in columns:
        add_column('username_key', 'VARCHAR(80)')
        db.session.execute(text('UPDATE "user" SET "username_key" = LOWER(LTRIM(username, \'@\')) WHERE "username_key" IS NULL'))
        # Prevent duplicate values from old data; suffix duplicates deterministically.
        rows = db.session.execute(text('SELECT id, username_key FROM "user" ORDER BY id')).fetchall()
        seen = {}
        for row in rows:
            key = (row[1] or '').strip().lower()
            if key in seen:
                key = f'{key}-{row[0]}'
                db.session.execute(text('UPDATE "user" SET "username_key" = :key WHERE id = :id'), {'key': key, 'id': row[0]})
            seen[key] = row[0]
        if is_pg:
            db.session.execute(text('ALTER TABLE "user" ALTER COLUMN "username_key" SET NOT NULL'))
            db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_username_key ON "user" ("username_key")'))
        else:
            # SQLite supports creating a unique index after backfill.
            db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_username_key ON "user" ("username_key")'))

    db.session.commit()


def _ensure_catalog_data():
    from .models import Category, ConfigType, Game
    defaults = {
        Category: [('Competitive','competitive'),('Public','public'),('Mix','mix'),('Training','training'),('Movement','movement'),('Performance','performance'),('Utility','utility'),('Other','other')],
        ConfigType: [('AIM','aim'),('NO RECOIL','no-recoil'),('BHOP','bhop'),('MOVEMENT','movement-type'),('CROSSHAIR','crosshair'),('FPS BOOST','fps-boost'),('CONFIG PACK','config-pack'),('OTHER','other-type')],
        Game: [('CS 1.6','cs-16'),('CS2','cs2'),('Counter-Strike','counter-strike')],
    }
    for model, rows in defaults.items():
        for name, slug in rows:
            if not model.query.filter_by(slug=slug).first():
                db.session.add(model(name=name, slug=slug))
    db.session.commit()


def _ensure_system_admin():
    from .models import User, Wallet
    if not current_app.config.get('ADMIN_BOOTSTRAP', True):
        return
    username = current_app.config.get('ADMIN_USERNAME','admin').strip().lstrip('@')
    email = current_app.config.get('ADMIN_EMAIL','admin@cwhub.local').strip().lower()
    admin = User.query.filter((User.username_key == username.casefold()) | (User.email.ilike(email))).first()
    if not admin:
        admin = User(username=username, username_key=username.casefold(), email=email, role='SUPER_ADMIN', is_verified=True, is_active_user=True)
        admin.set_password(current_app.config.get('ADMIN_PASSWORD','ChangeMe123!'))
        admin.wallet = Wallet()
        db.session.add(admin)
        db.session.commit()
    elif admin.role != 'SUPER_ADMIN' and admin.username_key == username.casefold():
        admin.role = 'SUPER_ADMIN'; admin.is_verified = True; admin.is_active_user = True
        db.session.commit()


def _repair_missing_columns():
    """Best-effort additive schema repair for existing deployments.
    Never drops data or alters existing columns. Each DDL operation has its own transaction.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateIndex
    inspector = inspect(db.engine)
    dialect = db.engine.dialect.name
    preparer = db.engine.dialect.identifier_preparer
    for table in db.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {c['name'] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            # Add as nullable to preserve old rows; application defaults handle new writes.
            type_sql = col.type.compile(dialect=db.engine.dialect)
            qtable = preparer.quote(table.name)
            qcol = preparer.quote(col.name)
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {qtable} ADD COLUMN {qcol} {type_sql}'))
            except Exception:
                logging.getLogger(__name__).exception('Schema repair: %s.%s', table.name, col.name)
    # Create missing single-column indexes where safe.
    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing_names = {i['name'] for i in inspector.get_indexes(table.name)}
        for idx in table.indexes:
            if idx.name in existing_names or len(idx.columns) != 1:
                continue
            try:
                with db.engine.begin() as conn:
                    conn.execute(CreateIndex(idx))
            except Exception:
                pass


def _ensure_business_catalog():
    from .models import SellerPlan
    defaults = [
        ('Bepul','bepul',0,15,5,False,False,'Boshlash uchun. 5 ta faol config.'),
        ('Pro','pro',29000,10,20,True,True,'Ko‘proq config, kamroq komissiya va ustuvor moderatsiya.'),
        ('Ultra','ultra',59000,7,50,True,True,'Professional sotuvchilar uchun yuqori limit va past komissiya.'),
    ]
    for name, slug, price, comm, limit, highlighted, priority, desc in defaults:
        if not SellerPlan.query.filter_by(slug=slug).first():
            db.session.add(SellerPlan(name=name, slug=slug, monthly_price=price, commission_rate=comm, product_limit=limit, highlighted=highlighted, priority_moderation=priority, description=desc))
    db.session.commit()


def create_app(config_class=BaseConfig):
    logging.basicConfig(level=logging.INFO)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, 'templates'),
        static_folder=os.path.join(project_root, 'static'),
        instance_relative_config=True,
    )
    app.config.from_object(config_class)
    app.jinja_env.undefined = ChainableUndefined
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

    from .models import User, SiteSettings, Notification, Announcement

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # Resilient asset endpoints: these keep dashboard styles/scripts available even if
    # a proxy/CDN/cache or static routing layer interferes with /static/*.
    @app.get('/assets/css/app.css')
    def assets_css():
        return send_from_directory(app.static_folder, 'css/app.css', max_age=300)

    @app.get('/assets/js/app.js')
    def assets_js():
        return send_from_directory(app.static_folder, 'js/app.js', max_age=300)

    @app.get('/assets/images/<path:filename>')
    def assets_image(filename):
        return send_from_directory(os.path.join(app.static_folder, 'images'), filename, max_age=300)

    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .marketplace import bp as marketplace_bp
    from .seller import bp as seller_bp
    from .admin import bp as admin_bp
    from .payments import bp as payments_bp
    from .orders import bp as orders_bp
    from .api import bp as api_bp
    from .business import bp as business_bp
    for bp in (auth_bp, main_bp, marketplace_bp, seller_bp, admin_bp, payments_bp, orders_bp, api_bp, business_bp):
        app.register_blueprint(bp)

    @app.before_request
    def maintenance_gate():
        # Texnik xizmat rejimida ham CSS/JS/rasmlar, favicon va health-check
        # bloklanmasligi shart. Aks holda maintenance/login sahifalari
        # oddiy HTML ko'rinishida ochilib, dizayn yo'qoladi.
        public_endpoints = {
            'assets_css', 'assets_js', 'assets_image',
            'static', 'healthz',
            'admin.dashboard', 'admin.settings',
            'auth.login', 'auth.logout',
        }
        if request.path.startswith('/static/') or request.path.startswith('/assets/'):
            return None
        if request.endpoint in public_endpoints:
            return None
        try:
            maintenance = SiteSettings.get_or_create().maintenance_mode
        except Exception:
            db.session.rollback()
            maintenance = False
        if maintenance and not (current_user.is_authenticated and current_user.is_admin):
            return render_template('maintenance.html'), 503
        return None

    @app.teardown_request
    def cleanup_db_session(exception=None):
        # Har bir requestdan so‘ng SQLAlchemy sessionni tozalash.
        # Exception bo‘lsa transactionni rollback qilamiz.
        if exception is not None:
            try:
                db.session.rollback()
            except Exception:
                pass
        db.session.remove()

    @app.after_request
    def security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if request.path.startswith(('/cart','/orders','/seller','/admin','/profile','/notifications','/payments')):
            response.headers.setdefault('Cache-Control', 'private, no-store')
        return response

    @app.template_filter('uz_status')
    def uz_status(value):
        mapping = {
            'PENDING':'Kutilmoqda','PROCESSING':'Jarayonda','APPROVED':'Tasdiqlangan','REJECTED':'Rad etilgan',
            'HIDDEN':'Yashirilgan','DELETED':'O‘chirilgan','COMPLETED':'Yakunlangan','CANCELLED':'Bekor qilingan',
            'REFUNDED':'Qaytarilgan','PAID':'To‘langan','PAYMENT_SUBMITTED':'Chek yuborilgan','PENDING_PAYMENT':'To‘lov kutilmoqda','USER':'Foydalanuvchi',
            'SELLER':'Sotuvchi','ADMIN':'Administrator','SUPER_ADMIN':'Super admin','ACTIVE':'Faol','DISABLED':'O‘chirilgan',
        }
        return mapping.get(str(value), str(value).replace('_',' ').title())

    @app.template_filter('uz_role')
    def uz_role(value):
        return {'USER':'Foydalanuvchi','SELLER':'Sotuvchi','ADMIN':'Administrator','SUPER_ADMIN':'Super admin'}.get(str(value), str(value))

    @app.template_filter('verified_badge')
    def verified_badge(value):
        return '✓' if value else ''

    @app.template_filter('seller_title_class')
    def seller_title_class(value):
        return {
            'Yangi sotuvchi':'seller-title-new',
            'O‘sayotgan sotuvchi':'seller-title-grow',
            'Pro sotuvchi':'seller-title-pro',
            'Top sotuvchi':'seller-title-top',
        }.get(str(value), 'seller-title-none')

    @app.context_processor
    def inject_globals():
        try:
            settings = SiteSettings.get_or_create()
        except Exception:
            db.session.rollback()
            settings = None
        unread = 0
        if current_user.is_authenticated:
            try:
                unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            except Exception:
                db.session.rollback()
                unread = 0
        active_announcement = None
        try:
            active_announcement = Announcement.query.filter_by(enabled=True).order_by(Announcement.created_at.desc()).first()
        except Exception:
            db.session.rollback()
            active_announcement = None
        support_url = app.config.get('SUPPORT_TELEGRAM','https://t.me/shokirjonshokirov').strip()
        if support_url.startswith('@'):
            support_url = 'https://t.me/' + support_url.lstrip('@')
        elif not support_url.startswith(('http://','https://')):
            support_url = 'https://t.me/' + support_url.lstrip('/')
        return {'site_settings': settings, 'unread_notifications': unread, 'support_telegram': support_url, 'support_telegram_handle': ('@' + support_url.rstrip('/').split('/')[-1]), 'active_announcement': active_announcement}

    @app.errorhandler(404)
    def e404(e): return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def e403(e): return render_template('errors/403.html'), 403

    @app.errorhandler(429)
    def e429(e): return render_template('errors/429.html'), 429

    @app.errorhandler(413)
    def e413(e): return render_template('errors/413.html'), 413

    @app.errorhandler(503)
    def e503(e): return render_template('maintenance.html'), 503

    @app.errorhandler(500)
    def e500(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    with app.app_context():
        try:
            db.create_all()
            db.session.commit()
        except Exception:
            db.session.rollback()
            logging.getLogger(__name__).exception('Database jadvallarini yaratish xatosi')
        for step_name, step in (
            ('schema repair', _repair_missing_columns),
            ('legacy user schema', _ensure_legacy_schema),
            ('catalog bootstrap', _ensure_catalog_data),
            ('business catalog bootstrap', _ensure_business_catalog),
            ('system admin bootstrap', _ensure_system_admin),
        ):
            try:
                step()
            except Exception:
                db.session.rollback()
                logging.getLogger(__name__).exception('Database bootstrap xatosi: %s', step_name)

    @app.get('/healthz')
    def healthz():
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            return jsonify({'ok': True, 'service': 'cwhub'})
        except Exception:
            db.session.rollback()
            return jsonify({'ok': False, 'service': 'cwhub'}), 503

    return app
