from ..models import SiteSettings,PaymentSettings
def settings(): return SiteSettings.get_or_create()
def payment_settings(): return PaymentSettings.get_or_create()
