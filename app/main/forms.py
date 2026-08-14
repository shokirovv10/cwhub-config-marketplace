from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class ProfileForm(FlaskForm):
    username = StringField('Foydalanuvchi nomi', validators=[DataRequired(), Length(3, 80)])
    nickname = StringField('Nik', validators=[Optional(), Length(max=120)])
    description = TextAreaField('O‘zingiz haqingizda', validators=[Optional(), Length(max=2000)])
    avatar = FileField('Profil rasmi', validators=[Optional(), FileAllowed(['png', 'jpg', 'jpeg', 'webp'], 'Faqat PNG/JPG/WEBP.')])
    submit = SubmitField('Saqlash')
