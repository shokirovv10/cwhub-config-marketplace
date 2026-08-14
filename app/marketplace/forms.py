from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DecimalField, SelectField, IntegerField, SubmitField, URLField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL

class SellerForm(FlaskForm):
    nickname = StringField('Seller nickname', validators=[DataRequired(), Length(3, 100)])
    description = TextAreaField('Tavsif', validators=[Optional(), Length(max=3000)])
    payout_info = TextAreaField('Payout / payout account', validators=[DataRequired(), Length(min=4, max=1000)])
    verification_document = FileField('Verification document', validators=[DataRequired(), FileAllowed(['png','jpg','jpeg','webp','pdf'], 'PNG/JPG/WEBP/PDF only.')])
    submit = SubmitField('Submit verification')

class ConfigForm(FlaskForm):
    name = StringField('Config nomi', validators=[DataRequired(), Length(3, 180)])
    short_description = StringField('Qisqa tavsif', validators=[Optional(), Length(max=300)])
    description = TextAreaField('Tavsif', validators=[Optional(), Length(max=10000)])
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    type_id = SelectField('Config type', coerce=int, validators=[DataRequired()])
    game_id = SelectField('Game', coerce=int, validators=[DataRequired()])
    version = StringField('Versiya', validators=[Optional(), Length(max=80)])
    price = DecimalField('Price (UZS)', places=2, validators=[DataRequired(), NumberRange(min=0)])
    tags = StringField('Teglar', validators=[Optional(), Length(max=500)])
    demo_url = URLField('Demo URL', validators=[Optional(), URL()])
    cover_image = FileField('Cover image', validators=[Optional(), FileAllowed(['png', 'jpg', 'jpeg', 'webp'], 'Faqat PNG/JPG/WEBP.')])
    config_file = FileField('Config file', validators=[Optional()])
    submit = SubmitField('Publish Config')

class ReviewForm(FlaskForm):
    rating = IntegerField('Rating', validators=[DataRequired(), NumberRange(min=1, max=5)])
    comment = TextAreaField('Comment', validators=[Optional(), Length(max=1500)])
    submit = SubmitField('Review')
