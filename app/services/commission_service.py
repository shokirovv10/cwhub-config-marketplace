from decimal import Decimal,ROUND_HALF_UP
Q=Decimal('0.01')
def split_amount(gross,rate):
    gross=Decimal(str(gross)); rate=Decimal(str(rate)); commission=(gross*rate/Decimal('100')).quantize(Q,ROUND_HALF_UP); return commission,gross-commission
