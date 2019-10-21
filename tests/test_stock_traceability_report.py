# This file is part stock_traceability_report module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unittest


from trytond.tests.test_tryton import ModuleTestCase
from trytond.tests.test_tryton import suite as test_suite


class StockTraceabilityReportTestCase(ModuleTestCase):
    'Test Stock Traceability Report module'
    module = 'stock_traceability_report'


def suite():
    suite = test_suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            StockTraceabilityReportTestCase))
    return suite
