# Dash app entry point
import dash
from dash import html
from .layout import create_layout
from .callbacks import register_callbacks

app = dash.Dash(__name__)
server = app.server

app.layout = create_layout()
register_callbacks(app)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)