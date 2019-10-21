# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import stock


def register():
    Pool.register(
        stock.PrintStockTraceabilityStart,
        module='stock_traceability_report', type_='model')
    Pool.register(
        stock.PrintStockTraceability,
        module='stock_traceability_report', type_='wizard')
    Pool.register(
        stock.PrintStockTraceabilitySReport,
        module='stock_traceability_report', type_='report')
