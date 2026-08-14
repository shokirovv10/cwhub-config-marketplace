This project uses Flask-Migrate. After installation run:

flask --app run.py db init
flask --app run.py db migrate -m "initial"
flask --app run.py db upgrade

For quick local development the app also calls db.create_all().
