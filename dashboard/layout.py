from dash import dcc, html
import datetime

def create_layout():
    return html.Div([
        html.H2("Activity Tracker Dashboard"),

        dcc.DatePickerSingle(
            id='date-picker',
            min_date_allowed=datetime.date(2025, 1, 1),
            max_date_allowed=datetime.date.today(),
            date=datetime.date.today()
        ),

        dcc.Graph(id="daily-bar"),
        html.Div(id="detail-box"),

        html.Hr(),

        html.Div([
            html.Div([
                # LEFT: Weekly Timeline + Cumulative
                html.Div([
                    html.H4("Weekly Timeline View"),
                    dcc.Graph(id="weekly-timeline", style={"width": "100%"}),
                    html.H4("Weekly Summary (Cumulative)"),
                    dcc.Graph(id="weekly-bar", style={"width": "100%"})
                ], style={"width": "48%", "display": "inline-block", "verticalAlign": "top"}),

                # RIGHT: Monthly Timeline + Cumulative
                html.Div([
                    html.H4("Monthly Timeline View"),
                    dcc.Graph(id="monthly-timeline", style={"width": "100%"}),
                    html.H4("Monthly Summary (Cumulative)"),
                    dcc.Graph(id="monthly-bar", style={"width": "100%"})
                ], style={"width": "48%", "display": "inline-block", "marginLeft": "4%", "verticalAlign": "top"})
            ])
        ], style={"marginTop": "20px"})

    ])