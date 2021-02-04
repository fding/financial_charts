"""An example financial data plotting application.

The application allows arbitrary number of plots (on the same axis).
For each plot, the x and y axis could represent any field of any stock.
Everything is reactive -- changes will automatically be reflected in the entire application.
"""

import functools

import edifice as ed
from edifice import Dropdown, IconButton, Label, ScrollView, Slider, TextInput, View
from edifice.components import plotting

from . import stock_charts
from . import option_charts


class App(ed.Component):

    def render(self):
        return ed.Window(title="Financial Charts")(
            ed.TabView(labels=["Stocks", "Options"])(
                stock_charts.StockCharts(),
                option_charts.OptionCharts(),
            )
        )


# Finally to start the the app, we pass the Component to the edifice.App object
# and call the start function to start the event loop.
if __name__ == "__main__":
    ed.App(App(), inspector=True).start()
