#!/usr/bin/python3
import re
import datetime
import calendar
from datetime import date, timedelta
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
    simulate_fund_account(loan, interest, start_date, 30, amortization)

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


class Mortgage:
    def __init__(self, amount, interest_rate):
        self.amount = amount
        self.interest_rate = interest_rate

    def amortize(self, amount):
        self.amount -= amount

    def monthly_interest(self):
        return (self.amount * self.interest_rate/Decimal(12)).quantize(Decimal('1.00'))

    # This is broken since tax depends on yearly interest expenses and we don't
    # know how to compute the amount of interest paid for the entire year.
    # But for the current simulation we can ignore that since we're never
    # paying more than 100,000 sek / year.
    def monthly_interest_after_tax_deduction(self):
        yearly_interest = (self.amount * self.interest_rate)*Decimal('0.7')
        return (yearly_interest/Decimal(12)).quantize(Decimal('1.00'))

    def clone(self):
        return Mortgage(self.amount, self.interest_rate)

class BasicFundAccount:
    def __init__(self, open_date):
        self.depot_value = Decimal(0)
        self.shares = 0
        self.current_date = open_date
        self.due_tax_deduction = Decimal(0)
        self.purchase_value = Decimal(0)
        self.realized_profits = Decimal(0)
        self.total_deposited = Decimal(0)

    def move_forward_to_day(self, day):
        if self.current_date.day > day:
            self.current_date = self.current_date.replace(day = 1)
            self.current_date += timedelta(months=1)
            self._enter_month(self.current_date.month)

        days_in_month = calendar.monthrange(self.current_date.year, self.current_date.month)[1]
        while days_in_month < day:
            self.current_date += timedelta(months=1)
            self._enter_month(self.current_date.month)
            days_in_month = calendar.monthrange(self.current_date.year, self.current_date.month)[1]

        self.current_date = self.current_date.replace(day = day)

    def next_month(self):
        self.current_date = self.current_date.replace(day = 1)
        self.current_date += relativedelta(months=1)
        self._enter_month(self.current_date.month)

    def current_value(self):
        return (self.current_share_price()*self.shares).quantize(Decimal('1.00'))

    def current_profit(self):
        return self.current_value() - self.purchase_value + self.realized_profits

    def current_share_price(self):
        return get_price(self.current_date)

    def deposit(self, amount):
        print("  adding to depot: %s" % amount)
        assert not amount.is_signed()
        self.depot_value += amount
        self.total_deposited += amount

    def buy_shares(self, count):
        assert count >= 0
        purchase_amount = self.current_share_price()*count
        assert self.depot_value >= purchase_amount
        self.shares += count
        self.depot_value -= purchase_amount
        self.purchase_value += purchase_amount

    def sell_shares(self, count):
        assert count >= 0
        assert count <= self.shares
        sell_amount = (self.current_share_price()*count).quantize(Decimal('1.00'))

        purchase_price = self.purchase_value / self.shares
        partial_purchase_value = purchase_price*count
        self.realized_profits += (sell_amount - partial_purchase_value).quantize(Decimal('1.00'))

        self.shares -= count
        self.depot_value += sell_amount
        self.purchase_value -= partial_purchase_value

    def _enter_month(self, month):
        if not self.due_tax_deduction.is_zero():
            print("  deducting tax: %s (%s available in depot)" % (self.due_tax_deduction, self.depot_value))
        assert self.due_tax_deduction <= self.depot_value
        assert not self.due_tax_deduction.is_signed()
        self.depot_value -= self.due_tax_deduction
        self.due_tax_deduction = Decimal(0)

class DirectFundAccount(BasicFundAccount):
    def __init__(self, open_date):
        BasicFundAccount.__init__(self, open_date)
        self.pending_tax_next_year = Decimal(0)

    def _enter_month(self, month):
        super()._enter_month(month)
        if month == 1:
            assert self.due_tax_deduction.is_zero()
            self.due_tax_deduction = self.pending_tax_next_year

            standard_income = self.current_value() * Decimal('0.004')
            pending_tax_next = standard_income * Decimal('0.3')
            pending_tax_next = pending_tax_next.quantize(Decimal('1.00'))
            print("Standard income tax next year: %s" % pending_tax_next)
            self.pending_tax_next_year = pending_tax_next


class InsuranceFundAccount(BasicFundAccount):
    def __init__(self, open_date):
        BasicFundAccount.__init__(self, open_date)
        self.amount_at_year_start = Decimal(0)
        self.year_deposit_first_half = Decimal(0)
        self.year_deposit_second_half = Decimal(0)
        self.tax_deducted_so_far = Decimal(0)

    def _enter_month(self, month):
        super()._enter_month(month)
        previous_amount_at_year_start = self.amount_at_year_start
        if month == 1:
            self.amount_at_year_start = self.current_value()
            print("Amount at start of %s: %s" % (self.current_date.year, self.amount_at_year_start))

        # > När dras avkastningsskatten?
        # > Den dras 4 ggr om året, i januari, april, juli och oktober.
        if month in (1, 4, 7, 10):
            # Predict how much tax we are going to pay at end of this year
            taxation_year = self.current_date.year
            if month == 1:
                taxation_year -= 1
            print('  Tax deduction calculation:')
            slr_date = date(taxation_year - 1, 11, 30)
            slr = get_slr(slr_date)
            slr_factor = slr + Decimal('0.01')
            if slr_factor < Decimal('0.0125'):
                slr_factor = Decimal('0.0125')
            print('    SLR factor: %s' % slr_factor)
            base_taxation_fund_amount = previous_amount_at_year_start
            print('    Base fund amount: %s' % base_taxation_fund_amount)
            taxation_deposits = self.year_deposit_first_half + self.year_deposit_second_half * Decimal(0.5)
            print('    Added deposit amount: %s' % taxation_deposits)
            taxation_fund_amount = base_taxation_fund_amount + taxation_deposits
            tax = (taxation_fund_amount * slr_factor * Decimal('0.3')).quantize(Decimal('1.00'))
            print("    Predicted tax at end of year: %s" % tax)

            # Make sure we have deducted at least a proportion of the predicted tax
            # that corresponds to the how many months have gone on the current
            # taxation year.
            if month == 1:
                due_tax_factor = Decimal('1.0')
            elif month == 10:
                due_tax_factor = Decimal('0.75')
            elif month == 7:
                due_tax_factor = Decimal('0.5')
            elif month == 4:
                due_tax_factor = Decimal('0.25')

            total_due_now = (tax * due_tax_factor).quantize(Decimal('1.00'))
            self.due_tax_deduction = total_due_now - self.tax_deducted_so_far
            self.tax_deducted_so_far += self.due_tax_deduction
            print("    Deduct now: %s" % self.due_tax_deduction)
            print("    Accumulated: %s" % self.tax_deducted_so_far)
            assert not self.due_tax_deduction.is_signed()

            if month == 1:
                self.year_deposit_first_half = Decimal(0)
                self.year_deposit_second_half = Decimal(0)
                self.tax_deducted_so_far = Decimal(0)

def simulate_mortgage(loan_amount, interest_rate, date_start, years, amortization):
    amortization = amortization.quantize(Decimal('1.00'))
    mortgage = Mortgage(loan_amount, interest_rate)

    csvfile = open('mortgage.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Interest',
        'Debt',
        'Total paid interest',
        'Total amortization',
        'Total paid',
        'Balance'
    ])

    current_date = date(year=date_start.year, month=date_start.month, day=25)
    date_end = date_start + relativedelta(years=years)
    total_paid_interest = Decimal(0)
    total_paid_amortization = Decimal(0)
    while current_date < date_end:
        monthly_interest = mortgage.monthly_interest_after_tax_deduction()
        mortgage.amortize(amortization)
        total_paid_interest += monthly_interest
        total_paid_amortization += amortization
        total_paid = total_paid_interest + total_paid_amortization

        row = [
            current_date,
            monthly_interest,
            mortgage.amount,
            total_paid_interest,
            total_paid_amortization,
            total_paid,
            -mortgage.amount - total_paid
        ]

        writer.writerow(row)
        current_date += relativedelta(months=1)

    csvfile.close()

def predict_deposits_until_january(actual_mortgage, faux_mortgage, current_month, amortization):
    faux_mortgage = faux_mortgage.clone()
    deposit_sum = Decimal(0)
    faux_mortgage.amortize(amortization)
    if current_month == 1:
        return deposit_sum
    #print("  predict:")
    while current_month != 13:
        deposit_adjustment = actual_mortgage.monthly_interest_after_tax_deduction() - \
            faux_mortgage.monthly_interest_after_tax_deduction()
        deposit = amortization - deposit_adjustment
        #print("    %s %s" % (current_month, deposit))
        deposit_sum += deposit
        faux_mortgage.amortize(amortization)
        current_month += 1
    return deposit_sum


def simulate_fund_account(loan_amount, interest_rate, date_start, years, faux_amortization):
    account = DirectFundAccount(date_start)
    faux_mortgage = Mortgage(loan_amount, interest_rate)
    faux_amortization = faux_amortization.quantize(Decimal('1.00'))
    actual_mortgage = Mortgage(loan_amount, interest_rate)

    end_date = date_start + relativedelta(years=years)

    total_paid_interest = Decimal(0)
    total_paid_tax = Decimal(0)

    csvfile = open('fund_account.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Faux interest',
        'Deposit',
        'Fund value',
        'Value after selling',
        'Total paid interest',
        'Total paid tax',
        'Total fund deposits',
        'Total paid',
        'Profit',
        'Profit tax',
        'Balance',
        'Remaining after repaying mortgage',
        'Shares'
    ])

    while account.current_date < end_date:
        account.move_forward_to_day(25)
        print(account.current_date)

        deposit = faux_mortgage.monthly_interest_after_tax_deduction() + faux_amortization
        deposit -= actual_mortgage.monthly_interest_after_tax_deduction()
        account.deposit(deposit)

        deposits_before_january = predict_deposits_until_january(actual_mortgage, faux_mortgage,
            account.current_date.month, faux_amortization)
        print("  approximate remaining deposit before tax: %s" % deposits_before_january)
        save_for_tax = Decimal(0)
        if deposits_before_january < account.pending_tax_next_year:
            save_for_tax = max(account.pending_tax_next_year, account.due_tax_deduction)

        print("  depot value: %s" % account.depot_value)
        print("    (saving %s for tax)" % save_for_tax)
        print("  current share price: %s" % account.current_share_price())

        available_for_purchase = account.depot_value
        available_for_purchase -= save_for_tax
        if not available_for_purchase.is_signed():
            shares_to_buy = available_for_purchase/account.current_share_price()
            shares_to_buy = shares_to_buy.to_integral_value(rounding=decimal.ROUND_FLOOR)
            account.buy_shares(shares_to_buy)
            print("  buy %s shares" % shares_to_buy)
            print("  fund value: %s" % account.current_value())

        total_paid_interest += actual_mortgage.monthly_interest_after_tax_deduction()
        total_paid = total_paid_interest + account.total_deposited
        total_paid_tax += account.due_tax_deduction

        profit = account.current_profit()
        profit_tax = profit*Decimal('0.3').quantize(Decimal('1.00'))
        value_after_selling = account.current_value() - profit_tax

        row = [
            account.current_date,
            faux_mortgage.monthly_interest_after_tax_deduction(),
            deposit,
            account.current_value(),
            value_after_selling,
            total_paid_interest,
            total_paid_tax,
            account.total_deposited,
            total_paid,
            profit,
            profit_tax,
            value_after_selling - total_paid_interest - loan_amount,
            value_after_selling - loan_amount,
            account.shares
        ]
        writer.writerow(row)

        faux_mortgage.amortize(faux_amortization)
        account.next_month()

    csvfile.close()

def simulate_kf(loan_amount, interest_rate, date_start, years, faux_amortization):
    account = InsuranceFundAccount(date_start)
    actual_mortgage = Mortgage(loan_amount, interest_rate)
    faux_mortgage = Mortgage(loan_amount, interest_rate)
    faux_amortization = faux_amortization.quantize(Decimal('1.00'))
    total_paid_interest = Decimal(0)
    total_paid_tax = Decimal(0)

    date_end = date_start + relativedelta(years=years)

    #rows = []
    csvfile = open('kf.csv', 'w', newline='')
    writer = csv.writer(csvfile)
    writer.writerow([
        'Date',
        'Faux interest',
        'Deposit',
        'Fund value',
        'Fund profit',
        'Total paid interest',
        'Total paid tax',
        'Total fund deposits',
        'Total paid',
        'Balance',
        'Remaining after repaying mortgage',
        'Shares'
    ])
    while account.current_date < date_end:
        account.move_forward_to_day(25)
        print("%s:" % account.current_date)
        deposit = faux_mortgage.monthly_interest_after_tax_deduction() + faux_amortization
        print("  would have paid %s to mortgage" % deposit)
        deposit -= actual_mortgage.monthly_interest_after_tax_deduction()
        account.deposit(deposit)

        if account.due_tax_deduction > account.depot_value:
            # Not enough money in depot. Need to sell off shares.
            extra_needed_money = account.due_tax_deduction - account.depot_value
            shares_to_sell = extra_needed_money / account.current_share_price()
            shares_to_sell = shares_to_sell.to_integral_value(rounding=decimal.ROUND_CEILING)
            account.sell_shares(shares_to_sell)
            print("  Sell %s shares to pay for tax; depot value now %s" % (shares_to_sell, account.depot_value))

        available_for_purchase = account.depot_value - account.due_tax_deduction
        shares_to_buy = available_for_purchase/account.current_share_price()
        shares_to_buy = shares_to_buy.to_integral_value(rounding=decimal.ROUND_FLOOR)
        if not shares_to_buy.is_zero():
            account.buy_shares(shares_to_buy)
            print("  Buy %s shares" % shares_to_buy)
            print("  Depot value: %s" % account.depot_value)

        print("  Fund value after transactions: %s" % account.current_value())
        total_paid_interest += actual_mortgage.monthly_interest_after_tax_deduction()
        total_paid = total_paid_interest + account.total_deposited
        total_paid_tax += account.due_tax_deduction

        row = [
            account.current_date,
            faux_mortgage.monthly_interest_after_tax_deduction(),
            deposit,
            account.current_value(),
            account.current_profit(),
            total_paid_interest,
            total_paid_tax,
            account.total_deposited,
            total_paid,
            account.current_value() - total_paid_interest - loan_amount,
            account.current_value() - loan_amount,
            account.shares
        ]
        writer.writerow(row)

        faux_mortgage.amortize(faux_amortization)
        account.next_month()

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
