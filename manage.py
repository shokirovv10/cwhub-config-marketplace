import click
from app import create_app
from app.extensions import db
from app import _ensure_catalog_data, _ensure_business_catalog, _ensure_system_admin, _repair_missing_columns
from app.models import User, Wallet

app = create_app()

@app.cli.command("init-db")
def init_db():
    """Production database bootstrap: jadvallar, moslashtirish va boshlang‘ich sozlamalar."""
    with app.app_context():
        try:
            db.create_all()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        steps = (
            _repair_missing_columns,
            _ensure_catalog_data,
            _ensure_business_catalog,
            _ensure_system_admin,
        )
        for step in steps:
            try:
                step()
            except Exception:
                db.session.rollback()
                raise
    click.echo("CwHUB: PostgreSQL/SQLite bazasi tayyor.")

@app.cli.command("reset-admin-password")
@click.option('--password', prompt='Yangi admin paroli', hide_input=True, confirmation_prompt=True)
def reset_admin_password(password):
    """SUPER_ADMIN parolini xavfsiz qayta o‘rnatish."""
    with app.app_context():
        username = app.config.get('ADMIN_USERNAME', 'admin').strip().lstrip('@')
        admin = User.query.filter_by(username_key=username.casefold()).first()
        if not admin:
            admin = User(username=username, username_key=username.casefold(), email=app.config.get('ADMIN_EMAIL', 'admin@cwhub.local'), role='SUPER_ADMIN', is_verified=True, is_active_user=True)
            admin.wallet = Wallet()
            db.session.add(admin)
        admin.role = 'SUPER_ADMIN'; admin.is_verified = True; admin.is_active_user = True; admin.set_password(password)
        db.session.commit()
        click.echo(f'Admin paroli yangilandi: {username}')

if __name__ == '__main__':
    app.run()
