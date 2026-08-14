from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class RegisterForm(FlaskForm):
    username = StringField('Foydalanuvchi nomi', validators=[DataRequired(), Length(3, 80)])
    email = StringField('Elektron pochta', validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField('Parol', validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField('Parolni tasdiqlang', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Ro‘yxatdan o‘tish')


class LoginForm(FlaskForm):
    identifier = StringField('Foydalanuvchi nomi yoki email', validators=[DataRequired()])
    password = PasswordField('Parol', validators=[DataRequired()])
    remember = BooleanField('Meni eslab qol')
    submit = SubmitField('Kirish')


class ForgotPasswordForm(FlaskForm):
    identifier = StringField('Foydalanuvchi nomi yoki email', validators=[DataRequired(), Length(max=255)])
    recovery_code = StringField('Tiklash kodi', validators=[DataRequired(), Length(min=8, max=128)])

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Yangi parol', validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField('Yangi parolni tasdiqlang', validators=[DataRequired(), EqualTo('password')])
