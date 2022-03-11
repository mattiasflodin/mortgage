#!/usr/bin/python3
import re
import datetime
from datetime import date
from unicodedata import decimal
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import csv

# can probably get more data from here https://rikatillsammans.se/historik/sixrx/

# Index: OMXS30GI, OMX Stockholm 30_GI, (SE0002402800)
# "Gross index" allegedly includes returns on shares, which is what
# Avanze Zero includes

def main():
    #decimal.getcontext().rounding = decimal.ROUND_HALF_UP

    prices = read_prices()
    loan = Decimal('3000000')
    amortization = Decimal(5000)
    years = 30
    amortization = loan/years/Decimal(12)
    interest = Decimal('0.03')
    start_date = date(1990, 3, 1)
    simulate_mortgage(loan, interest, start_date, years, amortization)
    simulate_kf(prices, loan, interest, start_date, years, amortization)

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

def simulate_kf(prices, loan_amount, interest, date_start, years, faux_amortization):
    faux_amortization = faux_amortization.quantize(Decimal('1.00'))
    actual_interest_amount = loan_amount * interest / Decimal(12)
    fund_amount = Decimal(0)
    total_paid_interest = Decimal(0)
    total_fund_deposits = Decimal(0)
    paid_amortization = Decimal(0)

    current_date = date(year=date_start.year, month=date_start.month, day=25)
    date_end = date_start + relativedelta(years=years)

    previous_index_price = prices[date_start]

    #rows = []
    csvfile = open('kf.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Fund growth amt',
        'Fund growth %',
        'Faux interest',
        'Deposit adjustment',
        'Deposit',
        'Fund value',
        'Total paid interest',
        'Total fund deposits',
        'Total paid',
        'Capital minus total paid'
    ])
    while current_date < date_end:
        #print(current_date)
        row = []
        row.append(current_date)

        current_index_price = get_price(prices, current_date)
        fund_growth_factor = current_index_price / previous_index_price
        new_fund_amount = fund_amount * fund_growth_factor
        new_fund_amount = new_fund_amount.quantize(Decimal('1.00'))
        previous_index_price = current_index_price
        row.append(new_fund_amount - fund_amount)
        row.append((fund_growth_factor*Decimal(100) - Decimal(100)).quantize(Decimal('1.000')))

        faux_interest_amount = (loan_amount*interest/Decimal(12)).quantize(Decimal('1.00'))
        deposit_penalty = faux_interest_amount - actual_interest_amount
        fund_deposit = faux_amortization + deposit_penalty
        fund_amount = new_fund_amount + fund_deposit
        fund_amount = fund_amount.quantize(Decimal('1.00'))
        loan_amount -= faux_amortization
        paid_amortization += faux_amortization

        row.append(faux_interest_amount)
        row.append(deposit_penalty)
        row.append(fund_deposit)
        row.append(fund_amount)

        total_paid_interest += actual_interest_amount
        row.append(total_paid_interest)
        total_fund_deposits += fund_deposit
        row.append(total_fund_deposits)
        total_paid = total_paid_interest + total_fund_deposits
        row.append(total_paid)
        row.append(fund_amount - total_paid - loan_amount)
        writer.writerow(row)

        current_date += relativedelta(months=1)

    csvfile.close()

def get_price(prices, date):
    price = prices.get(date)
    while price is None or price.is_zero():
        date -= relativedelta(days=1)
        price = prices.get(date)
    return price

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

if __name__ == "__main__":
    main()
