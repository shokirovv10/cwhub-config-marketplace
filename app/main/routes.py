from flask import render_template,request,redirect,url_for,flash,send_file,abort
from flask_login import login_required,current_user
from ..models import Config,Category,Game,Order,Notification,Announcement,User
from ..extensions import db
from ..services.storage_service import storage
from ..models import SellerProfile
from . import bp
@bp.route('/')
def index():
    popular=Config.query.filter_by(status='APPROVED').order_by(Config.download_count.desc()).limit(8).all(); latest=Config.query.filter_by(status='APPROVED').order_by(Config.created_at.desc()).limit(8).all(); sellers=[]
    sellers=SellerProfile.query.filter_by(approved=True).limit(6).all()
    announcement=Announcement.query.filter_by(enabled=True).order_by(Announcement.created_at.desc()).first()
    return render_template('index.html',popular=popular,latest=latest,sellers=sellers,categories=Category.query.all(),announcement=announcement)
@bp.route('/seller/<nickname>')
def seller_public(nickname):
    from ..models import SellerProfile,Review
    sp=SellerProfile.query.filter_by(nickname=nickname,approved=True).first_or_404(); configs=[c for c in sp.configs if c.status=='APPROVED']; ratings=[r.rating for c in configs for r in c.reviews]; avg=round(sum(ratings)/len(ratings),1) if ratings else 0
    from ..models import OrderItem
    sales_count=OrderItem.query.join(Order).filter(OrderItem.seller_id==sp.id,Order.status=='COMPLETED').count()
    return render_template('seller/public.html',seller=sp,configs=configs,avg=avg,sales_count=sales_count)
@bp.route('/notifications')
@login_required
def notifications():
    items=Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all(); Notification.query.filter_by(user_id=current_user.id,is_read=False).update({'is_read':True}); db.session.commit(); return render_template('notifications.html',items=items)
@bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)


@bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    from .forms import ProfileForm
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        username = (form.username.data or '').strip().lstrip('@')
        username_key = username.casefold()
        duplicate = User.query.filter(User.username_key == username_key, User.id != current_user.id).first()
        if duplicate:
            form.username.errors.append('Bu foydalanuvchi nomi allaqachon band.')
        else:
            current_user.set_username(username)
            current_user.nickname = (form.nickname.data or '').strip() or None
            current_user.description = (form.description.data or '').strip() or None
            avatar = form.avatar.data
            old_avatar = current_user.avatar
            if avatar and avatar.filename:
                if (avatar.mimetype or '').lower() not in {'image/png','image/jpeg','image/webp'}:
                    form.avatar.errors.append('Faqat PNG, JPG yoki WEBP rasm qabul qilinadi.')
                    return render_template('profile_edit.html', form=form)
                path, _, _ = storage().save(avatar, 'avatars', avatar.filename)
                current_user.avatar = path
                if old_avatar and old_avatar != path:
                    storage().delete(old_avatar)
            db.session.commit()
            flash('Profil ma’lumotlari saqlandi.', 'success')
            return redirect(url_for('main.profile'))
    return render_template('profile_edit.html', form=form)


@bp.get('/avatar/<int:id>')
def avatar(id):
    user = db.session.get(User, id) or abort(404)
    if not user.avatar or not storage().exists(user.avatar):
        abort(404)
    return send_file(user.avatar, conditional=True)

@bp.get('/kafolat-qoidalar')
def rules():
    return render_template('rules.html')

@bp.get('/yordam')
def support():
    return render_template('support.html')

@bp.get('/maxfiylik')
def privacy():
    return render_template('privacy.html')

@bp.get('/foydalanish-shartlari')
def terms():
    return render_template('terms.html')


@bp.route('/admin-bolish', methods=['GET', 'POST'])
@login_required
def admin_apply_info():
    from ..models import AdminApplication
    if request.method == 'POST':
        desired_role=(request.form.get('desired_role') or 'MODERATOR').strip()
        experience=(request.form.get('experience') or '').strip()
        motivation=(request.form.get('motivation') or '').strip()
        availability=(request.form.get('availability') or '').strip()
        if desired_role not in {'MODERATOR','SUPPORT','FINANCE'}:
            flash('Administratorlik yo‘nalishi noto‘g‘ri.', 'danger')
        elif len(experience)<20 or len(motivation)<20 or len(availability)<3:
            flash('Savollarga to‘liq va mazmunli javob bering.', 'danger')
        elif AdminApplication.query.filter_by(user_id=current_user.id,status='PENDING').first():
            flash('Sizda allaqachon ko‘rib chiqilayotgan ariza mavjud.', 'info')
        else:
            app=AdminApplication(user_id=current_user.id,desired_role=desired_role,experience=experience,motivation=motivation,availability=availability)
            db.session.add(app); db.session.commit(); flash('Administratorlik arizangiz yuborildi. Admin panelidagi arizalar bo‘limida ko‘rib chiqiladi.', 'success'); return redirect(url_for('main.profile'))
    return render_template('admin_apply.html')
