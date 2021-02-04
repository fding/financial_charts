import asyncio
import datetime
from dateutil import tz
import functools
import math

import edifice as ed
from edifice.components import plotting
import numpy as np
import pandas as pd
import yfinance as yf

from . import black_scholes


# Helper functions to access Yahoo Finance data and cache results
@functools.cache
def get_ticker(stock):
    return yf.Ticker(stock)

@functools.cache
def get_last_close(stock):
    return get_ticker(stock).info["regularMarketPreviousClose"]

@functools.cache
def get_expiries(stock):
    return get_ticker(stock).options

@functools.cache
def get_option_chain(stock, expiry):
    return get_ticker(stock).option_chain(expiry)

def days_till_expiration(expiration):
    return (datetime.datetime.now() - datetime.datetime.strptime(
        expiration, "%Y-%m-%d").replace(
            hour=16, minute=0, second=0, tzinfo=tz.gettz("ET"))).total_seconds()/(3600*24)


class OptionCharts(ed.Component):

    def __init__(self):
        super().__init__()
        self.ticker = ""
        self.expiries = []
        self.loading_expiries = False
        self.expiry = ""
        self.strike_price = ""
        self.option_chain = None
        self.loading_option_chain = False
        self.option_type = "Call"
        self.days_to_maturity = -1
        self.stock_price = 0
        self.last_close_price = None
        self.implied_vol = None

        self.xaxis = "stock_price"
        self.yaxis = "option_price"

    def get_option_chain(self, option_chains=None):
        option_chains = option_chains if option_chains is not None else self.option_chain
        option_type_index = 0 if self.option_type == "Call" else 1
        return option_chains[option_type_index]

    async def ticker_changed(self, text):
        self.set_state(ticker=text, expiry="", expiries=[], strike_price="", option_chain=None,
                       loading_expiries=True, loading_option_chain=True)
        expiries = await asyncio.to_thread(lambda: get_expiries(text))
        # By the time the fetch completes, more change events could have fired
        if text != self.ticker:
            return
        self.last_close_price = await asyncio.to_thread(lambda: get_last_close(text))
        if text != self.ticker:
            return

        if expiries:
            option_chain = await asyncio.to_thread(lambda: get_option_chain(text, expiries[0]))
        else:
            option_chain = None
        if text != self.ticker:
            return
        strike_price = self.get_option_chain(option_chain).strike.iloc[0]
        implied_vol = self.get_option_chain(option_chain).impliedVolatility.iloc[0] * 100
        if math.isnan(implied_vol):
            implied_vol = 1000.0
        self.set_state(expiries=expiries, option_chain=option_chain,
                       expiry=expiries[0], strike_price=strike_price,
                       implied_vol=implied_vol,
                       stock_price=self.last_close_price,
                       loading_expiries=False, loading_option_chain=False)

    async def expiry_changed(self, text):
        if text:
            self.set_state(expiry=text, loading_option_chain=True)
            option_chain = await asyncio.to_thread(lambda: get_option_chain(self.ticker, text))
            if text != self.expiry:
                return
            implied_vol = self.get_option_chain(option_chain).impliedVolatility.iloc[0] * 100
            if math.isnan(implied_vol):
                implied_vol = 1000.0
            self.set_state(option_chain=option_chain,
                           strike_price=self.get_option_chain(option_chain).strike.iloc[0],
                           implied_vol=implied_vol,
                           loading_option_chain=False,
                           days_to_maturity=days_till_expiration(text))

    def strike_changed(self, text):
        option_chain = self.get_option_chain()
        cur_vol = option_chain[option_chain.strike == float(text)].impliedVolatility.iloc[0] * 100
        self.set_state(strike_price=text,
                       implied_vol=cur_vol)

    def plot(self, ax):
        if not self.ticker or self.option_chain is None or self.strike_price == "":
            return
        cur_price = self.last_close_price
        price_space = np.linspace(cur_price / 2, cur_price * 2, 200)
        days_to_maturity = int(days_till_expiration(self.expiry))
        maturity_space = np.linspace(days_to_maturity, -0.1, 200)
        option_chain = self.get_option_chain()
        cur_vol = option_chain[option_chain.strike == float(self.strike_price)].impliedVolatility.iloc[0] * 100
        if math.isnan(cur_vol):
            cur_vol = 1000.0
        vol_space = np.linspace(cur_vol/2.0, cur_vol * 2.0, 200)

        def get_data(name, xaxis):
            if xaxis == "stock_price":
                args = [float(self.strike_price), -self.days_to_maturity * np.ones_like(price_space),
                        price_space, 0.01/365, self.implied_vol * np.ones_like(price_space)]
            elif xaxis == "days_to_expiration":
                args = [float(self.strike_price), -maturity_space,
                        float(self.stock_price) * np.ones_like(maturity_space),
                        0.01/365, self.implied_vol * np.ones_like(maturity_space)]
            elif xaxis == "implied_vol":
                args = [float(self.strike_price), -self.days_to_maturity * np.ones_like(vol_space),
                        float(self.stock_price) * np.ones_like(vol_space),
                        0.01/365, vol_space]
            name_to_func = {
                "delta": black_scholes.delta,
                "gamma": black_scholes.gamma,
                "vega": black_scholes.vega,
                "theta": black_scholes.theta,
            }
            if self.option_type == "Call":
                name_to_func["option_price"] = black_scholes.call_price
            else:
                name_to_func["option_price"] = black_scholes.put_price
            greek = name_to_func[name](*args)
            if self.option_type == "Put" and name == "delta":
                greek = -1 + greek
            return greek

        if self.xaxis == "stock_price":
            xdata = price_space
        elif self.xaxis == "days_to_expiration":
            xdata = maturity_space
        elif self.xaxis == "implied_vol":
            xdata = vol_space

        ax.plot(xdata, get_data(self.yaxis, self.xaxis))

    def render(self):
        values = ["option_price", "delta", "gamma", "theta", "vega",]
        days_to_maturity = None
        if self.expiry:
            days_to_maturity = int(days_till_expiration(self.expiry)) - 1
        expiry_loaded = self.ticker is not None and self.expiries != [] and not self.loading_expiries
        option_chain_loaded = (self.ticker is not None and self.option_chain is not None
                               and not self.loading_option_chain)

        if expiry_loaded and option_chain_loaded:
            option_chain = self.get_option_chain()
            implied_vol = option_chain[option_chain.strike == float(self.strike_price)].impliedVolatility.iloc[0] * 100
            if math.isnan(implied_vol):
                implied_vol = 1000.0
            args = [float(self.strike_price), -float(days_to_maturity),
                    float(self.last_close_price), 0.01 / 365, implied_vol]
            greeks = {
                "gamma": black_scholes.gamma(*args),
                "theta": black_scholes.theta(*args),
                "vega": black_scholes.vega(*args),
            }
            if self.option_type == "Call":
                greeks.update({
                    "delta": black_scholes.delta(*args),
                    "option_price": black_scholes.call_price(*args),
                })
            else:
                greeks.update({
                    "delta": black_scholes.delta(*args) - 1,
                    "option_price": black_scholes.put_price(*args),
                })

        return ed.View(style={"align": "top", "margin": 10})(
            ed.Label("Loading..." if self.loading_expiries or self.loading_option_chain else "",
                     style={"margin-bottom": 5}),
            ed.View(layout="row", style={"align": "left"})(
                ed.View(layout="row", style={"width": 200})(
                    ed.Label("Ticker"),
                    ed.TextInput(self.ticker, on_change=self.ticker_changed),
                    ed.Dropdown(str(self.option_type), options=["Call", "Put"],
                                on_select=lambda text: self.set_state(option_type=text)),
                ),
                expiry_loaded and ed.View(layout="row", style={"width": 170, "margin-left": 5})(
                    ed.Label("Expiry"),
                    ed.Dropdown(str(self.expiry), options=self.expiries, on_select=self.expiry_changed),
                ),
                option_chain_loaded and ed.View(layout="row", style={"width": 150, "margin-left": 5})(
                    ed.Label("Strike Price"),
                    ed.Dropdown(str(self.strike_price),
                            options=list(map(str, self.get_option_chain().strike)) if self.option_chain else [],
                            on_select=self.strike_changed),
                ),
            ),
            expiry_loaded and option_chain_loaded and ed.View(layout="row", style={"align": "left"})(
                ed.Label("X"),
                ed.Dropdown(selection=self.xaxis, options=["days_to_expiration", "stock_price", "implied_vol"],
                            on_select=lambda text: self.set_state(xaxis=text)),
                ed.Label("Y"),
                ed.Dropdown(selection=self.yaxis, options=values,
                            on_select=lambda text: self.set_state(yaxis=text)),
                self.xaxis != "stock_price" and ed.Label(f"Stock Price ({self.stock_price:.2f})"),
                self.xaxis != "stock_price" and ed.Slider(
                    self.stock_price, min_value=self.last_close_price / 3, max_value=self.last_close_price * 3 + 1,
                    on_change=lambda val: self.set_state(stock_price=val),
                ).set_key("stock_price_slider"),
                self.xaxis != "days_to_expiration" and ed.Label(f"Days to Maturity ({self.days_to_maturity:.1f})"),
                self.xaxis != "days_to_expiration" and ed.Slider(
                    self.days_to_maturity, min_value=days_to_maturity, max_value=-0.1,
                    on_change=lambda val: self.set_state(days_to_maturity=val),
                ).set_key("maturity_slider"),
                self.xaxis != "implied_vol" and ed.Label(f"Implied Vol ({self.implied_vol:.1f})"),
                self.xaxis != "implied_vol" and ed.Slider(
                    self.implied_vol, min_value=implied_vol/2, max_value=implied_vol*2 + 10,
                    on_change=lambda val: self.set_state(implied_vol=val),
                ).set_key("vol_slider"),
            ),
            expiry_loaded and option_chain_loaded and ed.View()(
                ed.Label("Option Greeks:", style={"font-size": 18}),
                ed.View(layout="row")(
                    ed.Label(f"<b>Days to maturity:</b> {days_to_maturity}"),
                    ed.Label(f"<b>Stock price:</b> ${self.last_close_price:.2f}\t"),
                    ed.Label(f"<b>Option price:</b> ${greeks['option_price']:.2f}\t\n"),
                    ed.Label(f"<b>Implied Vol:</b> {implied_vol:.0f}%\t"),
                ),
                ed.View(layout="row")(
                    ed.Label(f"<b>Delta:</b> {greeks['delta']:.2f}\t"),
                    ed.Label(f"<b>Gamma:</b> {greeks['gamma']:.3f}\t"),
                    ed.Label(f"<b>Theta:</b> {greeks['theta']:.3f}\t"),
                    ed.Label(f"<b>Vega:</b> {greeks['vega']:.2f}\t"),
                )
            ),
            expiry_loaded and option_chain_loaded and plotting.Figure(plot_fun=lambda ax: self.plot(ax)),
        )
