import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from preflight import validate

HEADER = 'ledger,period,voucher_id,source_line_id,account,booked_currency,debit,credit,transaction_currency\n'

def run(*rows):
    return validate(io.StringIO(HEADER+'\n'.join(rows)+'\n'))

class PreflightTests(unittest.TestCase):
    def test_multiple_lines_can_share_a_voucher_number(self):
        out = run('A,2026-11,0001,S1,Cash,CNY,7,,USD',
                  'A,2026-11,0001,S2,Sales,CNY,,7,EUR')
        self.assertEqual(out['vouchers'][0]['status'], 'pass')
        self.assertEqual(out['vouchers'][0]['voucher_id'], '0001')

    def test_same_number_different_scope(self):
        out = run('A,2026-11,1,S1,Cash,CNY,7,,', 'B,2026-11,1,S1,Sales,CNY,,7,',
                  'A,2026-12,1,S1,Sales,CNY,,7,')
        self.assertEqual(len(out['vouchers']), 3)
        self.assertTrue(all(v['status'] == 'review' for v in out['vouchers']))

    def test_reused_source_id_flags_both_vouchers(self):
        out = run('A,2026-11,V1,00012345678901234567,Cash,CNY,7,,',
                  'A,2026-11,V2,00012345678901234567,Sales,CNY,,7,')
        flagged = [i for i in out['issues'] if i['code']=='duplicate_source_line']
        self.assertEqual(flagged[0]['lines'], [2,3])
        self.assertEqual(flagged[0]['source_line_id'], '00012345678901234567')
        self.assertTrue(all(v['status'] == 'review' for v in out['vouchers']))

    def test_duplicate_within_voucher_does_not_get_silently_dropped(self):
        out = run('A,2026-11,1,S1,Cash,CNY,7,,', 'A,2026-11,1,S1,Cash,CNY,7,,',
                  'A,2026-11,1,S2,Sales,CNY,,14,')
        self.assertEqual(out['vouchers'][0]['status'], 'review')
        self.assertIsNone(out['vouchers'][0]['difference'])

    def test_exact_decimal(self):
        out = run('A,2026-11,1,S1,Cash,CNY,0.10,,', 'A,2026-11,1,S2,Cash,CNY,0.20,,',
                  'A,2026-11,1,S3,Sales,CNY,,0.30,')
        self.assertEqual(out['vouchers'][0]['difference'], '0.00')

    def test_missing_and_mixed_booked_values_never_pass(self):
        out = run('A,2026-11,1,S1,Cash,CNY,7,,USD', 'A,2026-11,1,S2,Sales,EUR,,7,EUR',
                  'A,2026-11,2,S3,Cash,,7,,USD', 'A,2026-11,2,S4,Sales,CNY,,7,EUR')
        self.assertEqual({i['code'] for i in out['issues']}, {'mixed_booked_currency','invalid_booked_currency'})
        self.assertTrue(all(v['difference'] is None for v in out['vouchers']))

    def test_rejects_wrong_row_amounts_and_month(self):
        out = run('A,2026-11,1,S1,Cash,CNY,7,7,', 'A,2026-00,2,S2,Cash,CNY,-7,,',
                  'A,2026-11,3,S3,Cash,CNY,,0,')
        self.assertEqual({i['code'] for i in out['issues']}, {'invalid_amount','invalid_scope'})

    def test_ill_formed_input_is_error(self):
        for data in ('', HEADER, HEADER+'too,few\n', HEADER+'"unterminated\n'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate(io.StringIO(data))

    def test_cli_demo_is_read_only_and_returns_findings(self):
        fixture = Path('examples/vouchers.csv')
        before = fixture.read_bytes()
        p = subprocess.run([sys.executable,'preflight.py',str(fixture)], capture_output=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual({i['code'] for i in out['issues']},
                         {'duplicate_source_line','unbalanced','invalid_booked_currency'})
        self.assertEqual(before, fixture.read_bytes())
