from app import create_app
from app.extensions import db
from app.models import User, Wallet, Category, ConfigType, Game, SiteSettings, PaymentSettings, Config


def main():
    app = create_app()
    with app.app_context():
        SiteSettings.get_or_create()
        PaymentSettings.get_or_create()

        admin = User.query.filter_by(username_key=app.config['ADMIN_USERNAME'].casefold()).first()
        if not admin:
            admin = User(username=app.config['ADMIN_USERNAME'], username_key=app.config['ADMIN_USERNAME'].casefold(), email=app.config['ADMIN_EMAIL'], role='SUPER_ADMIN', is_verified=True, is_active_user=True)
            admin.set_password(app.config['ADMIN_PASSWORD'])
            admin.wallet = Wallet()
            db.session.add(admin)

        category_data = [
            ('Competitive', 'competitive'),
            ('Public', 'public'),
            ('Mix', 'mix'),
            ('Training', 'training'),
            ('Movement', 'movement'),
            ('Performance', 'performance'),
            ('Utility', 'utility'),
            ('Other', 'other'),
        ]
        type_data = [
            ('AIM', 'aim'),
            ('NO RECOIL', 'no-recoil'),
            ('BHOP', 'bhop'),
            ('MOVEMENT', 'movement-type'),
            ('CROSSHAIR', 'crosshair'),
            ('FPS BOOST', 'fps-boost'),
            ('CONFIG PACK', 'config-pack'),
            ('OTHER', 'other-type'),
        ]
        game_data = [
            ('CS 1.6', 'cs-16'),
            ('CS2', 'cs2'),
            ('Counter-Strike', 'counter-strike'),
        ]
        for name, slug in category_data:
            if not Category.query.filter_by(slug=slug).first():
                db.session.add(Category(name=name, slug=slug))
        for name, slug in type_data:
            if not ConfigType.query.filter_by(slug=slug).first():
                db.session.add(ConfigType(name=name, slug=slug))
        for name, slug in game_data:
            if not Game.query.filter_by(slug=slug).first():
                db.session.add(Game(name=name, slug=slug))

        # If this database came from an older build, hide its seeded demo configs.
        old_seller = User.query.filter_by(username='demo_seller').first()
        if old_seller:
            db.session.delete(old_seller)
        for old in User.query.filter(User.username.ilike('demo%')).all():
            if old.username != app.config['ADMIN_USERNAME']:
                db.session.delete(old)
        Config.query.filter(Config.name.ilike('%demo%')).delete(synchronize_session=False)

        db.session.commit()
        print('Seed complete. Demo seller/config data is disabled.')
        print('SUPER ADMIN:', app.config['ADMIN_USERNAME'], '/', app.config['ADMIN_PASSWORD'])


if __name__ == '__main__':
    main()
