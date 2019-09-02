# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

try:
    from trytond.modules.sale_add_product_lines_wizard.tests.test_sale_add_product_lines_wizard import suite
except ImportError:
    from .test_sale_add_product_lines_wizard import suite

__all__ = ['suite']
