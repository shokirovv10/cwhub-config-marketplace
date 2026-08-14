from ..extensions import db
from ..models import Download,Order,OrderItem
from .storage_service import storage

def authorize(user,order_id,config_id):
    order=Order.query.filter_by(id=order_id,buyer_id=user.id,status='COMPLETED').first()
    if not order: raise PermissionError("Download ruxsati yo'q.")
    item=OrderItem.query.filter_by(order_id=order.id,config_id=config_id).first()
    if not item: raise PermissionError("Config bu orderda yo'q.")
    if not storage().exists(item.config.file_path): raise FileNotFoundError('Fayl topilmadi.')
    return order,item

def log_download(user,order,item,ip):
    try:
        item.config.download_count = (item.config.download_count or 0) + 1
        db.session.add(Download(user_id=user.id,config_id=item.config.id,order_id=order.id,ip=ip))
        db.session.commit()
    except Exception:
        db.session.rollback()
