from flask import Blueprint
bp = Blueprint('business', __name__)
from . import routes
