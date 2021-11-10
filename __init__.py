# This file is part of the sale_add_product_lines_wizard module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.pool import Pool
from . import sale


def register():
    Pool.register(
        sale.AddLinesSelectProduct,
        sale.AnalyticAccountEntry,
        module='sale_add_product_lines_wizard', type_='model')
    Pool.register(
        sale.AddLines,
        module='sale_add_product_lines_wizard', type_='wizard')
