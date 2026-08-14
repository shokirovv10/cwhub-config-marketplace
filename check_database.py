from app import create_app
from app.extensions import db
from sqlalchemy import text, inspect

app=create_app()
with app.app_context():
    db.session.execute(text("SELECT 1"))
    print("DATABASE OK")
    print("TABLES:", ", ".join(sorted(inspect(db.engine).get_table_names())))
