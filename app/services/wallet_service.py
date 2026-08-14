from decimal import Decimal
from ..extensions import db
from ..models import Wallet, WalletTransaction

POSITIVE_TYPES = {'SALE', 'BONUS', 'ADJUSTMENT', 'WITHDRAWAL_REJECTED'}


def ensure_wallet(user):
    if not user.wallet:
        user.wallet = Wallet()
        db.session.flush()
    return user.wallet


def post(wallet, tx_type, amount, ref_type=None, ref_id=None, description=''):
    amount = Decimal(str(amount))
    tx = WalletTransaction(
        wallet=wallet,
        tx_type=tx_type,
        amount=amount,
        reference_type=ref_type,
        reference_id=str(ref_id) if ref_id is not None else None,
        description=description,
    )
    db.session.add(tx)
    if tx_type in POSITIVE_TYPES:
        wallet.available_balance += amount
    elif tx_type == 'WITHDRAWAL':
        wallet.available_balance -= amount
        wallet.pending_balance += amount
    elif tx_type == 'WITHDRAWAL_REJECTED':
        wallet.pending_balance = max(Decimal('0'), Decimal(wallet.pending_balance) - amount)
    elif tx_type == 'WITHDRAWAL_COMPLETED':
        wallet.pending_balance = max(Decimal('0'), Decimal(wallet.pending_balance) - amount)
    elif tx_type == 'REFUND':
        wallet.available_balance -= amount
    return tx


def credit_sale(user, amount, order_id):
    wallet = ensure_wallet(user)
    post(wallet, 'SALE', amount, 'order', order_id, f'Sale earnings for order #{order_id}')
    wallet.total_earned += Decimal(str(amount))


def reserve_withdrawal(user, amount, withdrawal_id):
    wallet = ensure_wallet(user)
    amount = Decimal(str(amount))
    if Decimal(wallet.available_balance) < amount:
        raise ValueError('Balans yetarli emas.')
    return post(wallet, 'WITHDRAWAL', amount, 'withdrawal', withdrawal_id, f'Withdrawal hold #{withdrawal_id}')


def release_withdrawal(user, amount, withdrawal_id, rejected=False):
    wallet = ensure_wallet(user)
    return post(
        wallet,
        'WITHDRAWAL_REJECTED' if rejected else 'WITHDRAWAL_COMPLETED',
        amount,
        'withdrawal',
        withdrawal_id,
        f"Withdrawal {'rejected' if rejected else 'completed'} #{withdrawal_id}",
    )
