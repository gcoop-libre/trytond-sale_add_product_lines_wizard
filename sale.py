# This file is part of the sale_add_product_lines_wizard module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.modules.product import price_digits
from trytond.modules.analytic_account import AnalyticMixin
from trytond.wizard import Wizard, StateView, StateTransition, Button

__all__ = ['AddLinesSelectProduct', 'AddLines', 'AnalyticAccountEntry']


class AnalyticAccountEntry:
    __metaclass__ = PoolMeta
    __name__ = 'analytic.account.entry'

    @classmethod
    def _get_origin(cls):
        origins = super(AnalyticAccountEntry, cls)._get_origin()
        return origins + ['sale.add_lines.select_product']


class AddLinesSelectProduct(ModelView, AnalyticMixin):
    'Add Products to Sale: Select products'
    __name__ = 'sale.add_lines.select_product'
    selected_sales = fields.Integer('Selected Sales', readonly=True)
    ignored_sales = fields.Integer('Ignored Sales', readonly=True, states={
            'invisible': Eval('ignored_sales', 0) == 0,
            },
        help="The sales that won't be changed because they are not in a state "
        "that allows it.")
    product = fields.Many2One('product.product','Product',
        states={
            'readonly': Eval('selected_sales', 0) == 0,
            }, depends=['selected_sales'])
    total_amount = fields.Numeric('Total', digits=(16,
            Eval('currency_digits', 2)),  depends=['currency_digits'],
        required=True)
    dues = fields.Integer('Dues', required=True)
    square_meter = fields.Numeric('Square meter', price_digits, required=True)
    first_invoice_date = fields.Date('First invoice date', required=True)
    line_description = fields.Text('Line description')
    unit_price = fields.Numeric('Unit price', digits=price_digits,
        readonly=True)
    quantity = fields.Float('Quantity',
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits'], readonly=True)
    unit_digits = fields.Function(fields.Integer('Unit Digits'),
        'on_change_with_unit_digits')
    currency_digits = fields.Integer('Currency Digits')

    @classmethod
    def __setup__(cls):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        super(AddLinesSelectProduct, cls).__setup__()
        cls.product.domain = SaleLine.product.domain

    @staticmethod
    def default_currency_digits():
        Company = Pool().get('company.company')
        company = Transaction().context.get('company')
        if company:
            return Company(company).currency.digits
        return 2

    @staticmethod
    def default_unit_digits():
        return 2

    @staticmethod
    def default_total_amount():
        return Decimal('0')

    @staticmethod
    def default_quantity():
        return 1

    @fields.depends('product')
    def on_change_with_unit_digits(self, name=None):
        if self.product:
            return self.product.sale_uom.digits
        return 2

    @fields.depends('dues', 'square_meter')
    def on_change_with_quantity(self, name=None):
        quantity = 1
        if self.dues and self.square_meter:
            quantity = self.square_meter / self.dues
        return float(quantity)

    @fields.depends('dues', 'square_meter', 'total_amount')
    def on_change_with_unit_price(self, name=None):
        unit_price = Decimal('0')
        quantity = self.on_change_with_quantity()
        if self.dues and self.total_amount:
            unit_price = self.total_amount / self.dues
        if self.dues and self.total_amount and self.square_meter:
            unit_price = (self.total_amount / self.dues) / Decimal(quantity)
        return unit_price


class AddLines(Wizard):
    'Add multiple lines based on one Product to Sale'
    __name__ = 'sale.add_lines'
    start_state = 'select_product'
    select_product = StateView('sale.add_lines.select_product',
        'sale_add_product_lines_wizard.add_product_lines_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add_lines', 'tryton-ok', default=True),
            ])
    add_lines = StateTransition()

    @classmethod
    def __setup__(cls):
        super(AddLines, cls).__setup__()
        cls._allowed_sale_states = {'draft'}

    def default_select_product(self, fields):
        Sale = Pool().get('sale.sale')

        active_ids = Transaction().context['active_ids']
        selected_sales = Sale.search([
                ('id', 'in', active_ids),
                ('state', 'in', self._allowed_sale_states),
                ('lines', 'in', None),
                ], count=True)
        return {
            'selected_sales': selected_sales,
            'ignored_sales': len(active_ids) - selected_sales,
            'line_description': '',
            }

    def transition_add_lines(self):
        pool = Pool()
        Sale = pool.get('sale.sale')
        SaleLine = pool.get('sale.line')

        product = self.select_product.product
        dues = self.select_product.dues
        if not product:
            return 'end'

        sales = Sale.search([
                ('id', 'in', Transaction().context['active_ids']),
                ('state', 'in', self._allowed_sale_states),
                ])
        if not sales:
            return 'end'

        # It creates lines despite of write sales to don't generate a
        # concurrent edition exception if an user is editing the same sale
        to_create = []
        for sale in sales:
            for due in range(1, dues+1):
                line = SaleLine()
                line.sale = sale
                line.type = 'line'
                line.product = product
                line.quantity = self.select_product.quantity
                for fname in SaleLine.product.on_change:
                    if (not fname.startswith('_parent_sale')
                            and fname not in ('product', 'quantity')):
                        default_fname = getattr(SaleLine, 'default_%s' % fname,
                            None)
                        if default_fname:
                            setattr(line, fname, default_fname())
                        else:
                            setattr(line, fname, None)

                line.on_change_product()
                line.unit_price = sale.currency.round(self.select_product.unit_price)
                line.manual_delivery_date = self.select_product.first_invoice_date + relativedelta(months=due)
                line.analytic_accounts = self.select_product.analytic_accounts
                description = line.description
                if self.select_product.line_description:
                    description = self.select_product.line_description
                line.description = '%s. Period: %s. Payment %s de %s' % (
                    description,
                    line.manual_delivery_date.strftime('%Y-%m'),
                    str(due),
                    str(dues),
                    )
                to_create.append(line)
        if to_create:
            SaleLine.save(to_create)

        for sale in sales:
            if sale.untaxed_amount != self.select_product.total_amount:
                line_diff = self.select_product.total_amount - sale.untaxed_amount
                last_line = sale.lines[-1]
                line = SaleLine()
                line.sale = sale
                line.type = 'line'
                line.quantity = 1
                line.unit_price = line_diff
                line.manual_delivery_date = last_line.manual_delivery_date
                line.taxes = last_line.taxes
                line.description = last_line.manual_delivery_date
                line.description = last_line.description
                line.description += '. Ajuste'
                line.save()

        return 'end'
