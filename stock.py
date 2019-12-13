# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import os
from datetime import datetime
from sql.aggregate import Sum
from trytond.config import config
from trytond.model import fields, ModelView
from trytond.pool import Pool
from trytond.pyson import Bool, Eval
from trytond.wizard import Wizard, StateView, StateReport, Button
from trytond.transaction import Transaction
from trytond.modules.html_report.html_report import HTMLReport


__all__ = ['PrintStockTraceabilityStart', 'PrintStockTraceability',
    'PrintStockTraceabilitySReport']

BASE_URL = config.get('web', 'base_url')


class PrintStockTraceabilityStart(ModelView):
    'Print Stock Traceability Start'
    __name__ = 'stock.traceability.start'
    from_date = fields.Date('From Date',
        # domain=[('from_date', '<', Eval('to_date'))],
        states={
            'required': Bool(Eval('to_date', False)),
        }, depends=['to_date'])
    to_date = fields.Date('To Date',
        # domain=[('to_date', '>', Eval('from_date'))],
        states={
            'required': Bool(Eval('from_date', False)),
        }, depends=['from_date'])


class PrintStockTraceability(Wizard):
    'Print Stock Traceability'
    __name__ = 'stock.print_traceability'
    start = StateView('stock.traceability.start',
        'stock_traceability_report.print_stock_traceability_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
            ])
    print_ = StateReport('stock.traceability.report')

    def do_print_(self, action):
        context = Transaction().context
        data = {
            'from_date': self.start.from_date,
            'to_date': self.start.to_date,
            'model': context.get('active_model'),
            'ids': context.get('active_ids'),
            }
        return action, data


class PrintStockTraceabilitySReport(HTMLReport):
    __name__ = 'stock.traceability.report'

    @classmethod
    def get_context(cls, records, data):
        pool = Pool()
        Company = pool.get('company.company')
        t_context = Transaction().context

        context = super().get_context(records, data)
        context['company'] = Company(t_context['company'])
        return context

    @classmethod
    def prepare(cls, data):
        pool = Pool()
        Template = pool.get('product.template')
        Product = pool.get('product.product')
        Move = pool.get('stock.move')
        Location = pool.get('stock.location')

        try:
            Production = pool.get('production')
        except:
            Production = None
        try:
            Lot = pool.get('stock.lot')
        except:
            Lot = None

        move = Move.__table__()
        cursor = Transaction().connection.cursor()

        t_context = Transaction().context
        company_id = t_context.get('company')
        from_date = data.get('from_date') or datetime.min.date()
        to_date = data.get('to_date') or datetime.max.date()

        parameters = {}
        parameters['from_date'] = from_date
        parameters['to_date'] = to_date
        parameters['show_date'] = True if data.get('from_date') else False
        parameters['production'] = True if Production else False
        parameters['lot'] = True if Lot else False
        if BASE_URL:
            base_url = '%s/#%s' % (
                BASE_URL, Transaction().database.name)
        else:
            base_url = '%s://%s/#%s' % (
                t_context['_request']['scheme'],
                t_context['_request']['http_host'],
                Transaction().database.name
                )
        parameters['base_url'] = base_url

        # Locations
        warehouses = Location.search([
            ('type', '=', 'warehouse')
            ])
        location_suppliers = [l.id for l in Location.search(
            [('type', '=', 'supplier')])]
        location_customers = [l.id for l in Location.search([
            ('type', '=', 'customer')])]
        location_lost_founds = [l.id for l in Location.search([
            ('type', '=', 'lost_found')])]
        if Production:
            location_productions = [l.id for l in Location.search([
                ('type', '=', 'production')])]

        keys = ()
        if data.get('model') == 'product.template':
            grouping = ('product',)
            for template in Template.browse(data['ids']):
                for product in template.products:
                    keys += ((product, None),)
        elif data.get('model') == 'stock.lot':
            grouping = ('product', 'lot')
            Lot = pool.get('stock.lot')
            for lot in Lot.browse(data['ids']):
                keys += ((lot.product, lot),)

        def compute_quantites(sql_where):
            query = move.select(Sum(move.quantity), where=sql_where)
            cursor.execute(*query)
            total = cursor.fetchone()[0] or 0
            query = move.select(move.id.as_('move_id'), where=sql_where)
            cursor.execute(*query)
            move_ids = [m[0] for m in cursor.fetchall()]
            moves = Move.browse(move_ids)
            return total, moves

        records = []
        for key in keys:
            product = key[0]
            lot = key[1]

            # Initial stock
            initial_stock = 0
            context = {}
            context['stock_date_start'] = from_date
            if data.get('to_date'):
                context['stock_date_end'] = data.get('to_date')
            with Transaction().set_context(context):
                pbl = Product.products_by_location(
                    [w.storage_location.id for w in warehouses],
                    with_childs=False, grouping=grouping)
            for w in warehouses:
                key = ((w.storage_location.id, product.id, lot.id)
                    if lot else (w.storage_location.id, product.id))
                if pbl.get(key):
                    initial_stock += pbl[key]

            # supplier_incommings from_location = supplier
            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.from_location.in_(location_suppliers)))
            if lot:
                sql_where.append((move.lot == lot.id))
            supplier_incommings_total, supplier_incommings = compute_quantites(sql_where)

            # supplier_returns: to_location = supplier
            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.to_location.in_(location_suppliers)))
            if lot:
                sql_where.append((move.lot == lot.id))
            supplier_returns_total, supplier_returns = compute_quantites(sql_where)

            # customer_outgoing: to_location = customer
            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.to_location.in_(location_customers)))
            if lot:
                sql_where.append((move.lot == lot.id))
            customer_outgoings_total, customer_outgoings = compute_quantites(sql_where)

            # customer_return: from_location = customer
            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.from_location.in_(location_customers)))
            if lot:
                sql_where.append((move.lot == lot.id))
            customer_returns_total, customer_returns = compute_quantites(sql_where)

            if Production:
                # production_outs: to_location = production
                sql_where = ((move.product == product.id)
                    & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                    & (move.state == 'done') & (move.company == company_id)
                    & (move.from_location.in_(location_productions)))
                if lot:
                    sql_where.append((move.lot == lot.id))
                production_outs_total, production_outs = compute_quantites(sql_where)

                # production_ins: from_location = production
                sql_where = ((move.product == product.id)
                    & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                    & (move.state == 'done') & (move.company == company_id)
                    & (move.to_location.in_(location_productions)))
                if lot:
                    sql_where.append((move.lot == lot.id))
                production_ins_total, production_ins = compute_quantites(sql_where)

            # inventory
            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.from_location.in_(location_lost_founds)))
            if lot:
                sql_where.append((move.lot == lot.id))
            lost_found_from_total, lost_found_from = compute_quantites(sql_where)

            sql_where = ((move.product == product.id)
                & (move.effective_date >= from_date) & (move.effective_date <= to_date)
                & (move.state == 'done') & (move.company == company_id)
                & (move.to_location.in_(location_lost_founds)))
            if lot:
                sql_where.append((move.lot == lot.id))
            lost_found_to_total, lost_found_to = compute_quantites(sql_where)

            records.append({
                'product': product,
                'lot': lot,
                'initial_stock': initial_stock,
                'supplier_incommings_total': supplier_incommings_total,
                'supplier_incommings': supplier_incommings,
                'supplier_return_total': (-supplier_returns_total
                    if supplier_returns_total else 0),
                'supplier_returns': supplier_returns,
                'customer_outgoings_total': (-customer_outgoings_total
                    if customer_outgoings_total else 0),
                'customer_outgoings': customer_outgoings,
                'customer_returns_total': customer_returns_total,
                'customer_returns': customer_returns,
                'production_outs_total': (-production_outs_total
                    if Production else None),
                'production_outs': production_outs if Production else None,
                'production_ins_total': (production_ins_total
                    if Production else None),
                'production_ins': production_ins if Production else None,
                'lost_found_total': lost_found_from_total - lost_found_to_total,
                'lost_found_from_total': lost_found_from_total,
                'lost_found_from': lost_found_from,
                'lost_found_to_total': (-lost_found_to_total
                    if lost_found_to_total else None),
                'lost_found_to': lost_found_to,
                })
        return records, parameters

    @classmethod
    def execute(cls, ids, data):
        context = Transaction().context
        context['report_lang'] = Transaction().language
        context['report_translations'] = os.path.join(
            os.path.dirname(__file__), 'report', 'translations')

        with Transaction().set_context(**context):
            records, parameters = cls.prepare(data)
            return super(PrintStockTraceabilitySReport, cls).execute(ids, {
                    'name': 'stock.traceability.report',
                    'model': data['model'],
                    'records': records,
                    'parameters': parameters,
                    'output_format': 'html',
                    'report_options': {
                        'now': datetime.now(),
                        }
                    })
