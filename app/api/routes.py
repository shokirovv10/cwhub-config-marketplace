from flask import jsonify,request
from flask_login import login_required,current_user
from ..extensions import db
from ..models import Config,Category,Game,Order,SiteSettings
from ..services.order_service import create_order
from ..services.storage_service import storage
from . import bp
def ok(data=None,message='OK'): return jsonify({'success':True,'message':message,'data':data})
def err(message,status=400): return jsonify({'success':False,'message':message,'data':None}),status
@bp.get('/configs')
def configs():
 q=Config.query.filter_by(status='APPROVED'); s=request.args.get('q','').strip()
 if s:q=q.filter(Config.name.ilike(f'%{s}%'))
 return ok([{'id':c.id,'name':c.name,'slug':c.slug,'price':str(c.price),'game':c.game.name,'category':c.category.name,'seller':c.seller.nickname} for c in q.order_by(Config.created_at.desc()).limit(100)])
@bp.get('/categories')
def categories(): return ok([{'id':x.id,'name':x.name,'slug':x.slug} for x in Category.query.order_by(Category.name).all()])
@bp.get('/games')
def games(): return ok([{'id':x.id,'name':x.name,'slug':x.slug} for x in Game.query.order_by(Game.name).all()])
@bp.post('/orders')
@login_required
def order_create():
 data=request.get_json(silent=True) or {}; ids=data.get('config_ids',[])
 try: order=create_order(current_user,ids); return ok({'id':order.id,'code':order.order_code},'Order created'),201
 except ValueError as e: return err(str(e),400)
@bp.get('/orders/<int:id>')
@login_required
def order(id):
 o=Order.query.filter_by(id=id,buyer_id=current_user.id).first()
 if not o:return err('Order not found',404)
 return ok({'id':o.id,'code':o.order_code,'status':o.status,'amount':str(o.gross_amount)})


UPLOAD_KINDS = {'config_file','cover_image','seller_verification','payment_receipt','plan_payment_receipt'}

@bp.post('/uploads/chunk/init')
@login_required
def upload_chunk_init():
    data = request.get_json(silent=True) or {}
    filename = str(data.get('filename','')).strip()
    mime = str(data.get('mime',''))
    kind = str(data.get('kind',''))
    try: size = int(data.get('size',0))
    except Exception: size = 0
    if not filename or size <= 0 or kind not in UPLOAD_KINDS:
        return err('Yuklash ma’lumotlari noto‘g‘ri.', 400)
    limits = {'config_file': 32*1024*1024, 'cover_image': 8*1024*1024, 'seller_verification': 12*1024*1024, 'payment_receipt': 12*1024*1024, 'plan_payment_receipt': 12*1024*1024}
    if size > limits[kind]: return err('Fayl hajmi ruxsat etilgan limitdan katta.', 413)
    ext = filename.rsplit('.',1)[-1].lower() if '.' in filename else ''
    try:
        configured = {x.strip().lower().lstrip('.') for x in (SiteSettings.get_or_create().allowed_extensions or '').split(',') if x.strip()}
    except Exception:
        db.session.rollback()
        configured = set()
    allowed = {'config_file': configured or {'cfg','zip','rar','txt'}, 'cover_image': {'png','jpg','jpeg','webp'}, 'seller_verification': {'png','jpg','jpeg','webp','pdf'}, 'payment_receipt': {'png','jpg','jpeg','webp','pdf'}, 'plan_payment_receipt': {'png','jpg','jpeg','webp','pdf'}}[kind]
    if ext not in allowed: return err('Bu fayl turiga ruxsat berilmagan.',400)
    try: upload_id = storage().init_chunk(current_user.id, filename, size, mime, kind)
    except Exception as exc: return err(f'Yuklash boshlanmadi: {exc}',500)
    return ok({'upload_id':upload_id,'chunk_size':1024*1024,'total_chunks':(size+1024*1024-1)//(1024*1024)},'Yuklash boshlandi.')

@bp.post('/uploads/chunk')
@login_required
def upload_chunk():
    upload_id = request.form.get('upload_id','')
    chunk_index = request.form.get('chunk_index','')
    chunk = request.files.get('chunk')
    try: idx = int(chunk_index)
    except Exception: return err('Qism raqami noto‘g‘ri.',400)
    if not upload_id or not chunk: return err('Yuklash qismi topilmadi.',400)
    try:
        size = storage().write_chunk(upload_id,current_user.id,idx,chunk.stream.read())
        return ok({'index':idx,'size':size},'Qism qabul qilindi.')
    except PermissionError: return err('Yuklashga ruxsat yo‘q.',403)
    except Exception as exc: return err(f'Qism yuklanmadi: {exc}',500)

@bp.post('/uploads/chunk/complete')
@login_required
def upload_chunk_complete():
    data=request.get_json(silent=True) or {}
    upload_id=str(data.get('upload_id',''))
    try: total=int(data.get('total_chunks',0))
    except Exception: total=0
    if not upload_id or total<=0: return err('Yuklash yakunlash ma’lumotlari noto‘g‘ri.',400)
    try:
        path,meta=storage().complete_chunk(upload_id,current_user.id,total)
        return ok({'upload_id':upload_id,'filename':meta['filename'],'kind':meta['kind'],'size':meta['size']},'Fayl tayyor.')
    except PermissionError: return err('Yuklashga ruxsat yo‘q.',403)
    except Exception as exc: return err(f'Yuklash yakunlanmadi: {exc}',500)
