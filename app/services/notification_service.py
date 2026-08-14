from ..extensions import db
from ..models import Notification
def notify(user_id,title,message):
    db.session.add(Notification(user_id=user_id,title=title,message=message))
