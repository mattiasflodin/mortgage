#!/usr/bin/python3
import re
import datetime
from datetime import date
from unicodedata import decimal
from dateutil.relativedelta import relativedelta
import decimal
from decimal import Decimal
from bisect import bisect
import csv

# can probably get more data from here https://rikatillsammans.se/historik/sixrx/

# Index: OMXS30GI, OMX Stockholm 30_GI, (SE0002402800)
# "Gross index" allegedly includes returns on shares, which is what
# Avanze Zero includes

g_prices = {}
g_govt_interest_rates = []

def main():
    #decimal.getcontext().rounding = decimal.ROUND_HALF_UP
    global g_prices, g_govt_interest_rates
    g_prices = read_prices()
    g_govt_interest_rates = read_government_interest_rate()

    loan = Decimal('3000000')
    amortization = Decimal(5000)
    years = 30
    amortization = loan/years/Decimal(12)
    interest = Decimal('0.03')
    start_date = date(1990, 3, 1)
    simulate_mortgage(loan, interest, start_date, years, amortization)
    simulate_kf(loan, interest, start_date, years, amortization)

def read_prices():
    date_re = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
    # This is not a CSV file, someone at Nasdaq is on drugs.
    with open('_SE0000337842_2022-03-10.csv') as f:
        values = f.read()
    values = values.split(';')
    values = values[1:] # remove "sep=;"

    row_iterator = chunks(values, 7)
    #print(next(row_iterator))
    prices = {}
    next(row_iterator)
    for row in row_iterator:
        date = row[0]
        closing = row[3]
        m = date_re.match(date)
        date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        try:
            closing = Decimal(closing.replace(',', ''))
        except Exception:
            print("cannot parse '%s'" % closing)
        prices[date] = closing
        #print(date, closing)
    return prices

def read_government_interest_rate():
    first_date_re = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')
    second_date_re = re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})')
    interest_rates = []
    with open('slr-historisk-statslaneranta.csv') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            d, interest, _ = row
            m = first_date_re.match(d)
            if m is not None:
                month, day, year = m.groups()
                day = int(day, 10)
                month = int(month, 10)
                year = int(year, 10)
            else:
                m = second_date_re.match(d)
                year, month, day = m.groups()
                day = int(day, 10)
                month = int(month, 10)
                year = int(year, 10)
            assert month <= 12
            assert year < 2022 and year > 1980
            assert day >= 1 and day <= 31

            d = date(year, month, day)
            interest_rates.append((d, Decimal(interest)))

    interest_rates.sort(key=lambda r: r[0])
    return interest_rates


def simulate_mortgage(loan_amount, interest, date_start, years, amortization):
    amortization = amortization.quantize(Decimal('1.00'))

    csvfile = open('mortgage.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Interest',
        'Debt',
        'Total paid interest',
        'Total amortization',
        'Total paid',
        'Capital minus total paid'
    ])

    current_date = date(year=date_start.year, month=date_start.month, day=25)
    date_end = date_start + relativedelta(years=years)
    total_paid_interest = Decimal(0)
    total_paid_amortization = Decimal(0)
    while current_date < date_end:
        row = []
        row.append(current_date)

        interest_amount = (loan_amount * interest / Decimal(12)).quantize(Decimal('1.00'))
        row.append(interest_amount)
        loan_amount -= amortization
        row.append(loan_amount)

        total_paid_interest += interest_amount
        total_paid_amortization += amortization
        row.append(total_paid_interest)
        row.append(total_paid_amortization)
        total_paid = total_paid_interest + total_paid_amortization
        row.append(total_paid)
        row.append(loan_amount.copy_negate() - total_paid)

        writer.writerow(row)
        current_date += relativedelta(months=1)

    csvfile.close()

def simulate_kf(loan_amount, interest, date_start, years, faux_amortization):
    faux_amortization = faux_amortization.quantize(Decimal('1.00'))
    actual_interest_amount = loan_amount * interest / Decimal(12)
    fund_shares = 0
    depot_value = Decimal(0)
    total_paid_interest = Decimal(0)
    total_paid_tax = Decimal(0)
    total_fund_deposits = Decimal(0)
    paid_amortization = Decimal(0)

    current_year = date_start.year
    current_date = date(year=date_start.year, month=date_start.month, day=25)
    date_end = date_start + relativedelta(years=years)

    fund_amount_at_year_start = {current_year: Decimal(0)}
    fund_deposits_first_half = Decimal(0)
    fund_deposits_second_half = Decimal(0)
    running_tax_deduction = Decimal(0)

    #rows = []
    csvfile = open('kf.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Faux interest',
        'Deposit adjustment',
        'Deposit',
        'Fund value',
        'Total paid interest',
        'Total paid tax',
        'Total fund deposits',
        'Total paid',
        'Capital minus total paid'
    ])
    while current_date < date_end:
        print("%s:" % current_date)
        row = []
        row.append(current_date)

        if current_year != current_date.year:
            # Record fund value at start of year and reset accumulation of
            # fund deposits by year half (for taxation calculations)
            current_year = current_date.year
            share_price_at_year_start = get_price(date(current_year, 1, 1))
            fund_amount = (share_price_at_year_start*fund_shares + depot_value).quantize(Decimal('1.00'))
            print("Fund at start of %d: %s" % (current_year, fund_amount))
            fund_amount_at_year_start[current_year] = fund_amount

        tax_deduction_due_now = Decimal(0)
        # > När dras avkastningsskatten?
        # > Den dras 4 ggr om året, i januari, april, juli och oktober.
        if current_date.month in (1, 4, 7, 10):
            # Predict how much tax we are going to pay at end of this year
            taxation_year = current_year
            if current_date.month == 1:
                taxation_year -= 1
            print('  Tax deduction calculation:')
            slr_date = date(taxation_year - 1, 11, 30)
            slr = get_slr(slr_date)
            slr_factor = slr + Decimal('0.01')
            if slr_factor < Decimal('0.0125'):
                slr_factor = Decimal('0.0125')
            print('    SLR factor: %s' % slr_factor)
            base_taxation_fund_amount = fund_amount_at_year_start[taxation_year]
            print('    Base fund amount: %s' % base_taxation_fund_amount)
            taxation_deposits = fund_deposits_first_half + fund_deposits_second_half * Decimal(0.5)
            print('    Added deposit amount: %s' % taxation_deposits)
            taxation_fund_amount = base_taxation_fund_amount + taxation_deposits
            tax = (taxation_fund_amount * slr_factor * Decimal('0.3')).quantize(Decimal('1.00'))
            print("    Predicted tax at end of year: %s" % tax)

            # Make sure we have deducted at least a proportion of the predicted tax
            # that corresponds to the how many months have gone on the current
            # taxation year.
            if current_date.month == 1:
                due_tax_factor = Decimal('1.0')
            elif current_date.month == 10:
                due_tax_factor = Decimal('0.75')
            elif current_date.month == 7:
                due_tax_factor = Decimal('0.5')
            elif current_date.month == 4:
                due_tax_factor = Decimal('0.25')

            total_due_now = (tax * due_tax_factor).quantize(Decimal('1.00'))
            tax_deduction_due_now = total_due_now - running_tax_deduction
            assert not tax_deduction_due_now.is_signed()
            print("    Deduct now: %s" % tax_deduction_due_now)
            print("    Accumulated: %s" % (running_tax_deduction + tax_deduction_due_now))
            running_tax_deduction += tax_deduction_due_now

            if current_date.month == 1:
                fund_deposits_first_half = Decimal(0)
                fund_deposits_second_half = Decimal(0)
                running_tax_deduction = Decimal(0)

        current_share_price = get_price(current_date)

        faux_interest_amount = (loan_amount*interest/Decimal(12)).quantize(Decimal('1.00'))
        deposit_adjustment = faux_interest_amount - actual_interest_amount
        # NEXT add funds to depot instead and then use depot value for any decisions made
        depot_deposit = faux_amortization + deposit_adjustment
        depot_value += depot_deposit

        if current_date.month < 7:
            fund_deposits_first_half += depot_deposit
        else:
            fund_deposits_second_half += depot_deposit

        #fund_deposit = faux_amortization + deposit_adjustment - tax_deduction_due_now
        print("  Adding to depot: %s" % depot_deposit)

        if tax_deduction_due_now > depot_value:
            # Not enough money in depot. Need to sell off shares.
            extra_needed_money = tax_deduction_due_now - depot_value
            shares_to_sell = extra_needed_money / current_share_price
            shares_to_sell = shares_to_sell.to_integral_value(rounding=decimal.ROUND_CEILING)
            fund_shares -= shares_to_sell
            sold_shares_value = (shares_to_sell*current_share_price).quantize(Decimal('1.00'))
            depot_value += sold_shares_value
            print("  Sell %s shares for %s to pay for tax; depot value now %s" % (shares_to_sell, sold_shares_value, depot_value))

        if not tax_deduction_due_now.is_zero():
            depot_value -= tax_deduction_due_now
            print("  Deducting tax from depot; value now %s" % depot_value)

        shares_to_buy = depot_value/current_share_price
        shares_to_buy = shares_to_buy.to_integral_value(rounding=decimal.ROUND_FLOOR)
        purchase_value = (shares_to_buy*current_share_price).quantize(Decimal('1.00'))
        if not shares_to_buy.is_zero():
            fund_shares += shares_to_buy
            depot_value -= purchase_value
            print("  Buy %s shares for %s" % (shares_to_buy, purchase_value))
            print("  Depot value: %s" % depot_value)

        new_fund_value = (fund_shares*current_share_price).quantize(Decimal('1.00'))

        loan_amount -= faux_amortization
        paid_amortization += faux_amortization

        row.append(faux_interest_amount)
        row.append(deposit_adjustment)
        row.append(depot_deposit)
        row.append(new_fund_value)
        print("  Fund value after transactions: %s" % new_fund_value)
        print("  Depot value: %s" % depot_value)

        total_paid_interest += actual_interest_amount
        row.append(total_paid_interest)
        total_paid_tax += tax_deduction_due_now
        row.append(total_paid_tax)
        total_fund_deposits += depot_deposit
        # TODO probably need to track paid tax here also
        row.append(total_fund_deposits)
        total_paid = total_paid_interest + total_fund_deposits
        row.append(total_paid)
        row.append(new_fund_value - total_paid - loan_amount)
        writer.writerow(row)

        previous_row_date = current_date
        current_date += relativedelta(months=1)

    csvfile.close()

def get_price(date):
    price = g_prices.get(date)
    while price is None or price.is_zero():
        date -= relativedelta(days=1)
        price = g_prices.get(date)
    return price

def get_govt_interest_rate_broken_bisect(date):
    pos = bisect(g_govt_interest_rates, date, key=lambda x: x[0])
    assert pos != len(g_govt_interest_rates)
    assert pos > 0
    if g_govt_interest_rates[pos][0] > date:
        pos -= 1
    assert pos > 0
    return g_govt_interest_rates[pos][1] / Decimal(100)

def get_slr(date):
    for (i, (d, rate)) in enumerate(g_govt_interest_rates):
        if d > date:
            return g_govt_interest_rates[i-1][1] / Decimal(100)

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

if __name__ == "__main__":
    main()
