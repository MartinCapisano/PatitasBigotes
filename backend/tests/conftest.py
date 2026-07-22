"""Shared environment defaults for the whole backend test suite.

`MERCADOPAGO_ENABLED` defaults to false in production so a misconfigured
environment falls on the safe side (see `db/config.get_mercadopago_enabled`).
The MercadoPago suite, however, exists to test MercadoPago: it runs with the
provider switched on, which is also what proves the pause is reversible and
did not change any of its behaviour. The lock itself is covered by
`test_mercadopago_disabled_lock.py`, which turns the flag off explicitly.
"""
import os

os.environ.setdefault("MERCADOPAGO_ENABLED", "true")

# Bank transfer data is required to boot (`config.validate_bank_transfer_config`)
# because the shop cannot be paid without it. These are the values the suite
# asserts against; `test_bank_transfer_instructions.py` overrides them where the
# point of the test is the configuration itself.
os.environ.setdefault("BANK_TRANSFER_ALIAS", "test.alias")
os.environ.setdefault("BANK_TRANSFER_CBU", "0000000000000000000000")
os.environ.setdefault("BANK_TRANSFER_BANK_NAME", "Test Bank")
os.environ.setdefault("BANK_TRANSFER_HOLDER", "Test Holder")
os.environ.setdefault("BANK_TRANSFER_CUIT", "20-12345678-9")
os.environ.setdefault("WHATSAPP_NUMBER", "5493511234567")
