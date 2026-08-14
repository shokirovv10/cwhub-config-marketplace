from flask import render_template
from flask_login import login_required,current_user
from ..models import Order
from . import bp
@bp.get('/')
@login_required
def index(): return render_template('orders/list.html',orders=Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all())
@bp.get('/<int:id>')
@login_required
def detail(id): return render_template('orders/detail.html',order=Order.query.filter_by(id=id,buyer_id=current_user.id).first_or_404())
