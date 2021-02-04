from autograd import elementwise_grad

import autograd.numpy as anp
import autograd.scipy.special as sp

def normal_cdf(x):
    return (1 + sp.erf(x / anp.sqrt(2))) / 2

def call_price(strike_price, days_to_expiry, stock_price, interest_rate, volatility):
    # Convert annualized volatility in percent to daily vol
    volatility = volatility / anp.sqrt(365.25) / 100
    sqrt_time = anp.sqrt(days_to_expiry)
    d1 = (anp.log(stock_price / strike_price)
          + (interest_rate + anp.square(volatility) / 2) * days_to_expiry) / (volatility * sqrt_time)
    d2 = d1 - volatility * sqrt_time
    # Black Scholes Formula
    return (stock_price * normal_cdf(d1)
            - strike_price * anp.exp(-interest_rate * days_to_expiry) * normal_cdf(d2))

def put_price(strike_price, days_to_expiry, stock_price, interest_rate, volatility):
    return strike_price * anp.exp(-interest_rate * days_to_expiry) - stock_price + \
            call_price(strike_price, days_to_expiry, stock_price, interest_rate, volatility)

# The Options Greeks
delta = elementwise_grad(call_price, argnum=2)
gamma = elementwise_grad(delta, argnum=2)
_theta_grad = elementwise_grad(call_price, argnum=1)
theta = lambda *args: -_theta_grad(*args)
vega = elementwise_grad(call_price, argnum=4)
