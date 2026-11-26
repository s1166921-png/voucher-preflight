"""Check a generic voucher CSV without modifying it or connecting to a ledger."""
import argparse
from collections import defaultdict
import csv
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re
import sys

SCOPE = ('ledger', 'period', 'voucher_id')
REQUIRED = (*SCOPE, 'source_line_id', 'account', 'booked_currency', 'debit', 'credit')


def money(value):
    if not value:
        return Decimal(0)
    if not re.fullmatch(r'[0-9]{1,24}(?:\.[0-9]{1,12})?', value):
        raise ValueError('expected a nonnegative decimal with a dot and no grouping')
    return Decimal(value)


def validate(stream):
    reader = csv.reader(stream, strict=True)
    sources, vouchers, issues = defaultdict(list), {}, []
    count = 0

    def issue(code, lines, **fields):
        issues.append({'code': code, 'lines': lines, **fields})

    def scope(key):
        return dict(zip(SCOPE, key))

    try:
        header = next(reader, [])
        if not set(REQUIRED).issubset(header) or len(header) != len(set(header)) or '' in header:
            raise ValueError('expected distinct columns: ' + ','.join(REQUIRED))
        while True:
            line = reader.line_num + 1
            data = next(reader, None)
            if data is None:
                break
            if not data:
                continue
            if len(data) != len(header):
                raise ValueError(f'line {line}: wrong number of columns')
            count += 1
            row = dict(zip(header, (cell.strip() for cell in data)))
            key = tuple(row[col] for col in SCOPE)
            if (not all(key) or not re.fullmatch(r'(?!0000)[0-9]{4}-(?:0[1-9]|1[0-2])', key[1])):
                issue('invalid_scope', [line], **scope(key))
                continue
            entry = vouchers.setdefault(key, {'lines': [], 'items': [], 'blocked': False})
            entry['lines'].append(line)
            source = row['source_line_id']
            currency = row['booked_currency']
            fields = [code for code, invalid in (
                ('missing_source_line_id', not source),
                ('missing_account', not row['account']),
                ('invalid_booked_currency', not re.fullmatch('[A-Z]{3}', currency)),
            ) if invalid]
            try:
                debit, credit = money(row['debit']), money(row['credit'])
                if (debit > 0) == (credit > 0):
                    raise ValueError('exactly one side must be positive')
            except ValueError:
                fields.append('invalid_amount')
            if source:
                sources[(*key[:2], source)].append((key, line))
            if fields:
                entry['blocked'] = True
                for code in fields:
                    issue(code, [line], **scope(key))
            else:
                entry['items'].append((currency, debit, credit))
    except csv.Error as exc:
        raise ValueError(f'near line {reader.line_num}: malformed CSV ({exc})') from exc
    if not count:
        raise ValueError('no voucher data rows')

    for (ledger, period, source), evidence in sources.items():
        if len(evidence) > 1:
            issue('duplicate_source_line', [line for _, line in evidence], ledger=ledger,
                  period=period, source_line_id=source)
            for key, _ in evidence:
                vouchers[key]['blocked'] = True

    report = []
    with localcontext() as ctx:
        ctx.prec = 64
        for key, entry in vouchers.items():
            currencies = sorted({row[0] for row in entry['items']})
            debit = credit = difference = None
            blocked = entry['blocked']
            if len(currencies) > 1:
                issue('mixed_booked_currency', entry['lines'], **scope(key), currencies=currencies)
                blocked = True
            if not blocked:
                debit = sum((d for _, d, _ in entry['items']), Decimal(0))
                credit = sum((c for _, _, c in entry['items']), Decimal(0))
                difference = debit - credit
                if difference:
                    issue('unbalanced', entry['lines'], **scope(key), difference=format(difference, 'f'))
            fmt = lambda value: None if value is None else format(value, 'f')
            report.append({**scope(key), 'lines': entry['lines'],
                           'status': 'review' if blocked or difference else 'pass',
                           'booked_currency': currencies[0] if not blocked else None,
                           'debit': fmt(debit), 'credit': fmt(credit), 'difference': fmt(difference)})
    return {'version': 1, 'input_rows': count, 'vouchers': report, 'issues': issues}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('voucher_csv', type=Path)
    args = cli.parse_args(argv)
    try:
        with args.voucher_csv.open(encoding='utf-8-sig', newline='') as f:
            report = validate(f)
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
