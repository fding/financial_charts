"""An example financial data plotting application.

The application allows arbitrary number of plots (on the same axis).
For each plot, the x and y axis could represent any field of any stock.
Everything is reactive -- changes will automatically be reflected in the entire application.
"""

import functools

import edifice as ed
from edifice import Dropdown, IconButton, Label, ScrollView, Slider, TextInput, View
from edifice.components import plotting

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.cm import get_cmap
import numpy as np
import pandas as pd
import yfinance as yf
import csv

plt.style.use('ggplot')

TICKERS = pd.read_csv("nasdaqlisted.txt", sep="|").Symbol


def data_for_ticker(ticker):
    return yf.Ticker(ticker).history("1y")


def _create_state_for_plot(plotname):
    """Creates the state associated with a particular plot."""
    return {
        # Data to show on x-axis (data type, data source)
        f"{plotname}.xaxis.data": ("Date", "AAPL"),
        # Transformation applied to x-axis (transform type, transform param)
        f"{plotname}.xaxis.transform": ("None", 30),
        f"{plotname}.yaxis.data": ("Close", "AAPL"),
        f"{plotname}.yaxis.transform": ("None", 30),
        f"{plotname}.color.data": ("Date", "AAPL"),
        f"{plotname}.color.transform": ("None", 30),
        f"{plotname}.size.data": ("Date", "AAPL"),
        f"{plotname}.size.transform": ("None", 30),
        # Plot type (line or scatter) and plot color
        f"{plotname}.type": "line",
        f"{plotname}.colormap": "peru",
    }

def merge(d1, d2):
    """Helper function to merge two dictionaries."""
    d = d1.copy()
    d.update(d2)
    return d

cmaps = ["viridis", "plasma", "inferno", "magma", "cividis", "jet", "rainbow", "gnuplot", "gnuplot2"]


# We store application state centrally. Each component can query this central store and
# set state, and all components that use that state will automatically update.
# See https://www.pyedifice.org/state.html
app_state = ed.StateManager(merge(_create_state_for_plot("plot0"), {
    "all_plots": ["plot0"],
    "next_i": 1,
}))

TRANSFORMS = {
    "None": ("", lambda x, p: x),
    "Return (abs)": ("Period", lambda x, p: x.diff(p)),
    "Return (rel)": ("Period", lambda x, p: x.pct_change(p)),
    "EMA": ("Half Life", lambda x, p: x.ewm(halflife=p).mean()),
    "EMSTD": ("Half Life", lambda x, p: x.ewm(halflife=p).std()),
}


# We create a component which describes the options for each axis (data source, transform).
# Since this component owns no state, we can simply write a render function and use the
# make_component decorator.
@ed.make_component
def AxisDescriptor(self, name, key, children):
    # We subscribe to app_state, so that state changes would trigger a re-render
    # Subscribe returns the data stored in app_state
    data = app_state.subscribe(self, f"{key}.data")
    data_type, ticker = data.value
    transform = app_state.subscribe(self, f"{key}.transform")
    transform_type, param = transform.value
    # We can use CSS styling. See https://www.pyedifice.org/styling.html
    row_style = {"align": "left", "width": 350}
    completer = ed.Completer(TICKERS)
    return View(layout="column")(
        View(layout="row", style=row_style)(
            Label(name, style={"width": 40}),
            Dropdown(selection=data_type, options=["Constant", "Date", "Close", "Volume"],
                     on_select=lambda text: data.set((text, ticker))),
            # if data_type != "Date", the following evaluates to False due to and short-circuiting.
            # A False or None child is treated as an empty slot
            data_type != "Date" and data_type != "Constant" and TextInput(
                text=ticker, style={"padding": 2},
                completer=completer,
                # The on_change callback is called whenever the change event fires,
                # i.e. when the input box text changes.
                on_change=lambda text: data.set((data_type, text))
            )
        ),
        View(layout="row", style=row_style)(
            Label("Transform:", style={"width": 70}),
            Dropdown(selection=transform_type, options=list(TRANSFORMS.keys()),
                     on_select=lambda text: transform.set((text, param))),
            TRANSFORMS[transform_type][0] and Label(f"{TRANSFORMS[transform_type][0]} ({param} days)", style={"width": 120}),
            TRANSFORMS[transform_type][0] and Slider(
                value=param, min_value=1, max_value=90, dtype=int,
                on_change=lambda val: transform.set((transform_type, val))
            )
        )
    )


# We create a shorthand for creating a component with a label
def labeled_elem(label, comp):
    return View(layout="row", style={"align": "left"})(
        Label(label, style={"width": 80}), comp,
    )

def add_divider(comp):
    return View(layout="column")(
        comp,
        View(style={"height": 0, "border": "1px solid gray"})
    )


# Now we make a component to describe the entire plot: the descriptions of both axis,
# plot type, and color
@ed.make_component
def PlotDescriptor(self, name, children):
    plot_type = app_state.subscribe(self, f"{name}.type")
    color = app_state.subscribe(self, f"{name}.colormap")
    def plot_type_changed(text):
        update_dict = {f"{name}.type": text}
        if text == "scatter" and plot_type.value != "scatter":
            update_dict.update({f"{name}.colormap": "viridis"})
        elif text != "scatter" and plot_type.value == "scatter":
            update_dict.update({f"{name}.colormap": "peru"})
        app_state.update(update_dict)

    return View(layout="row", style={"margin": 5})(
        View(layout="row") (
            View(layout="column", style={"align": "top"})(
                AxisDescriptor("x-axis", f"{name}.xaxis"),
                plot_type.value != "histogram" and AxisDescriptor("y-axis", f"{name}.yaxis"),
            ),
            plot_type.value == "scatter" and View(layout="column", style={"align": "top"})(
                AxisDescriptor("color", f"{name}.color"),
                AxisDescriptor("size", f"{name}.size"),
            ),
        ),
        View(layout="column", style={"align": "top", "margin-left": 10})(
            labeled_elem(
                "Chart type",
                Dropdown(selection=plot_type.value, options=["scatter", "line", "histogram"],
                         on_select=plot_type_changed)
            ),
            labeled_elem(
                "Color Map",
                Dropdown(selection=color.value, options=(list(mcolors.CSS4_COLORS.keys()) if plot_type.value != "scatter" else cmaps),
                         on_select=lambda text: color.set(text))
            )
        ),
    )


# Finally, we create a component that contains the plot descriptions, a button to add a plot,
# and the actual Matplotlib figure.
# To better organize the code, we create a class so that we can put plotting logic in methods.
class StockCharts(ed.Component):

    # Adding a plot is very simple conceptually (and in Edifice).
    # Just add new state for the new plot!
    def add_plot(self, e):
        next_key = "plot" + str(app_state["next_i"])
        app_state.update(merge(_create_state_for_plot(next_key), {
            "all_plots": app_state["all_plots"] + [next_key],
            "next_i": app_state["next_i"] + 1,
        }))

    # The Plotting function called by the plotting.Figure component.
    # The plotting function is passed a Matplotlib axis object.
    def plot(self, ax):
        all_plots = app_state["all_plots"]

        def get_data(df, label, transform, param):
            if label == "Constant":
                return np.ones_like(df.index)
            if label == "Date":
                return df.index
            return TRANSFORMS[transform][1](df[label], param)

        for plot in all_plots:
            plot_type = app_state.subscribe(self, f"{plot}.type").value
            color = app_state.subscribe(self, f"{plot}.colormap").value
            data_descriptors = {}
            transform_descriptors = {}
            if plot_type == "scatter":
                axes = ["yaxis", "color", "size"]
            elif plot_type == "histogram":
                axes = []
            else:
                axes = ["yaxis"]
            for axis in ["xaxis"] + axes:
                data_descriptors[axis] = app_state.subscribe(self, f"{plot}.{axis}.data").value
                transform_descriptors[axis] = app_state.subscribe(self, f"{plot}.{axis}.transform").value

            dfs = {}
            for axis in ["xaxis"] + axes:
                dfs[axis] = data_for_ticker(data_descriptors[axis][1])

            df = pd.DataFrame({"xaxis": get_data(dfs["xaxis"], data_descriptors["xaxis"][0], *transform_descriptors["xaxis"])},
                              index=dfs["xaxis"].index)

            for axis in axes:
                df = df.merge(pd.DataFrame({axis: get_data(dfs[axis], data_descriptors[axis][0], *transform_descriptors[axis])},
                                           index=dfs[axis].index),
                              left_index=True, right_index=True)
            df = df.dropna()
            if len(df) == 0:
                return

            if plot_type == "line":
                ax.plot(df.xaxis, df.yaxis, color=color)
            elif plot_type == "scatter":
                min_size = np.min(df["size"])
                max_size = np.max(df["size"])
                df["size"] = 1 + 40 * (df["size"] - min_size) / (max_size - min_size)
                ax.scatter(df.xaxis, df.yaxis, c=df.color, s=df["size"], cmap=get_cmap(color))
            elif plot_type == "histogram":
                ax.hist(df.xaxis, bins=int(len(df.xaxis) / 20), color=color)

    def render(self):
        all_plots = app_state.subscribe(self, "all_plots").value
        return View(layout="column", style={"margin": 10})(
            ScrollView(layout="column")(
                *[add_divider(PlotDescriptor(plotname)) for plotname in all_plots]
            ),
            # Edifice comes with Font-Awesome icons for your convenience
            IconButton(name="plus", title="Add Plot", on_click=self.add_plot),
            # We create a lambda fuction so that the method doesn't compare equal to itself.
            # This forces re-renders everytime this entire component renders.
            plotting.Figure(lambda ax: self.plot(ax)),
        )
